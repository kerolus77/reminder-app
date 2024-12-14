import json
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from tkcalendar import DateEntry
import threading
import time
from datetime import datetime
import uuid
import queue
from playsound import playsound


REMINDERS_FILE = "reminders.json"
class Reminder:
    def __init__(self, title, description, trigger_time):
        """
        Initialize a reminder with unique ID, title, description, and trigger time
        """
        self.id = str(uuid.uuid4())  # Unique identifier for each reminder
        self.title = title
        self.description = description
        self.trigger_time = trigger_time
        self.is_active = True  # Determines if the reminder is active or expired
        
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "trigger_time": self.trigger_time.strftime("%Y-%m-%d %H:%M"),
            "is_active": self.is_active,
        }

    @staticmethod
    def from_dict(data):
        return Reminder(
            title=data["title"],
            description=data["description"],
            trigger_time=datetime.strptime(data["trigger_time"], "%Y-%m-%d %H:%M"),
            reminder_id=data["id"],
            is_active=data["is_active"],
        )

class ReminderApp:
    def __init__(self, master):
        """
        Initialize the GUI Reminder Application
        """
        self.master = master
        master.title("Reminder App")
        master.geometry("360x640")  # Mobile-sized screen
        

        # Reminder Management
        self.reminders = {}
        self.monitoring_threads = {}
        self.reminders_lock = threading.Lock()
        self.notification_queue = queue.Queue()
        self.stop_event = threading.Event()

        # Load Images
        self._load_images()

        # Create Screens
        self.main_screen = tk.Frame(master)
        self.add_screen = tk.Frame(master)
        
        # Create UI Components
        self._create_main_screen()
        self._create_add_screen()
        self._load_reminders()
        # Start on Main Screen
        self._show_screen(self.main_screen)

        # Start notification handler thread
        self.notification_thread = threading.Thread(
            target=self._handle_notifications,
            daemon=True
        )
        self.notification_thread.start()
        
    def _load_reminders(self):
        """
        Load reminders from the JSON file into the app.
        """
        try:
            with open(REMINDERS_FILE, "r") as file:
                reminders_data = json.load(file)
                for reminder_data in reminders_data:
                    # Create Reminder objects from the JSON data
                    reminder = Reminder(
                        title=reminder_data["title"],
                        description=reminder_data["description"],
                        trigger_time=datetime.strptime(reminder_data["trigger_time"], "%Y-%m-%d %H:%M"),
                    )
                    reminder.id = reminder_data["id"]
                    reminder.is_active = reminder_data["is_active"]

                    # Skip past reminders
                    if datetime.now() > reminder.trigger_time:
                        reminder.is_active = False

                    self.reminders[reminder.id] = reminder

                    # Start monitoring active reminders
                    if reminder.is_active:
                        thread = threading.Thread(target=self._monitor_reminder, args=(reminder,), daemon=True)
                        self.monitoring_threads[reminder.id] = thread
                        thread.start()

            print("Reminders loaded successfully.")
        except FileNotFoundError:
            print("No reminders file found. Starting fresh.")
        except Exception as e:
            print(f"Error loading reminders: {e}")

        # Refresh the UI to display loaded reminders
        self._refresh_list()

    def _save_reminders(self):
        """
        Save all reminders to a file.
        """
        try:
            with open(REMINDERS_FILE, "w") as file:
                reminders_data = [reminder.to_dict() for reminder in self.reminders.values()]
                json.dump(reminders_data, file, indent=4)
            print("Reminders saved successfully.")
        except Exception as e:
            print(f"Error saving reminders: {e}")

    def _load_images(self):
        """
        Load and resize images for use in the app
        """
        self.add_icon = ImageTk.PhotoImage(Image.open("add.png").resize((20, 20)))
        self.trash_icon = ImageTk.PhotoImage(Image.open("trash.png").resize((20, 20)))
        self.back_icon = ImageTk.PhotoImage(Image.open("logout.png").resize((20, 20)))
        self.title_icon= ImageTk.PhotoImage(Image.open("title.png").resize((20, 20)))
        self.description_icon= ImageTk.PhotoImage(Image.open("des.png").resize((20, 20)))
        self.date_icon= ImageTk.PhotoImage(Image.open("calendar.png").resize((20, 20)))
        self.clock_icon= ImageTk.PhotoImage(Image.open("clock.png").resize((20, 20)))
        self.edit_icon = ImageTk.PhotoImage(Image.open("document.png").resize((20, 20)))

    def _show_screen(self, screen):
        """
        Show the specified screen and hide others
        """
        self.main_screen.pack_forget()
        self.add_screen.pack_forget()
        screen.pack(fill=tk.BOTH, expand=True)

    def _create_main_screen(self):
        """
        Create the Main Screen UI with a fixed Add Reminder button at the top
        and a scrollable area for the reminders.
        """
        # Main container frame
        main_frame = tk.Frame(self.main_screen)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Fixed Top Frame for Add Reminder Button
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=5)

        add_button = ttk.Button(
            button_frame,
            text="Add Reminder",
            command=lambda: self._show_screen(self.add_screen),
            image=self.add_icon,
            compound="left"
        )
        add_button.pack(side=tk.LEFT, padx=5)

        # Scrollable Frame for Reminders
        list_frame = tk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # Create a Canvas for Scrollable Area
        self.canvas = tk.Canvas(list_frame)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Vertical Scrollbar for the Canvas
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")

        # Configure Canvas to Use Scrollbar
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind('<Configure>', self._update_canvas_width)

        # Frame Inside the Canvas to Contain Reminder Cards
        self.reminder_list = tk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.reminder_list, anchor="nw")

        # Enable Mouse Wheel Scrolling
        self.master.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _update_canvas_width(self, event):
        """
        Update the width of the canvas and reminder_list dynamically to match the parent frame.
        """
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas.create_window((0, 0), window=self.reminder_list, anchor="nw"), width=canvas_width)
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))  # Update scroll region when width changes

    def _create_add_screen(self):
        """
        Create the Add Reminder Screen UI
        """
        input_frame = ttk.Frame(self.add_screen)
        input_frame.pack(fill=tk.Y, padx=20, pady=20)

        # Title Input
        ttk.Label(input_frame, text="Reminder Title:",image=self.title_icon,compound='left').pack(anchor='w', pady=(0, 5))
        self.title_entry = ttk.Entry(input_frame, width=40)
        self.title_entry.pack(pady=(0, 10))

        # Description Input
        ttk.Label(input_frame, text="Description:",image=self.description_icon,compound='left').pack(anchor='w', pady=(0, 5))
        self.description_entry = tk.Text(input_frame, height=4, width=30)
        self.description_entry.pack(pady=(0, 10))

        # Date Picker
        ttk.Label(input_frame, text="Select Date:",image=self.date_icon,compound='left').pack(anchor='w', pady=(0, 5))
        self.date_picker = DateEntry(
            input_frame,
            width=30,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='yyyy-mm-dd'
        )
        self.date_picker.pack(pady=(0, 10))

        # Time Input
        ttk.Label(input_frame, text="Time (HH:MM):",image=self.clock_icon,compound='left').pack(anchor='w', pady=(0, 5))
        self.time_entry = ttk.Entry(input_frame, width=30)
        self.time_entry.pack(pady=(0, 10))

        # Buttons
        button_frame = ttk.Frame(self.add_screen)
        button_frame.pack(pady=10)

        add_button = ttk.Button(
            button_frame,
            text="Add Reminder",
            command=self._add_reminder,
            image=self.add_icon,
            compound="left"
        )
        add_button.pack(side=tk.LEFT, padx=5)

        back_button = ttk.Button(
            button_frame,
            text="Back to Main Screen",
            command=lambda: self._show_screen(self.main_screen),
            image=self.back_icon,
            compound="left"
        )
        back_button.pack(side=tk.LEFT, padx=5)

    def _add_reminder(self):
        """
        Add a new reminder or update an existing one from input fields.
        """
        title = self.title_entry.get().strip()
        description = self.description_entry.get("1.0", tk.END).strip()
        date_str = self.date_picker.get()
        time_str = self.time_entry.get().strip()

        if not title:
            messagebox.showerror("Error", "Title cannot be empty")
            return

        try:
            # Parse the entered date and time
            trigger_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

            # Check if the entered time is in the past
            if trigger_time < datetime.now():
                messagebox.showerror("Error", "You cannot set a reminder in the past.")
                return

            with self.reminders_lock:
                if hasattr(self, 'editing_reminder_id') and self.editing_reminder_id:
                    # Editing an existing reminder
                    reminder_id = self.editing_reminder_id
                    reminder = self.reminders[reminder_id]
                    reminder.title = title
                    reminder.description = description
                    reminder.trigger_time = trigger_time
                    reminder.is_active = True  # Reset to active
                    self.editing_reminder_id = None  # Reset editing state
                    print(f"Reminder {reminder_id} updated successfully.")
                else:
                    # Adding a new reminder
                    reminder = Reminder(title, description, trigger_time)
                    self.reminders[reminder.id] = reminder

                    # Start monitoring thread
                    thread = threading.Thread(target=self._monitor_reminder, args=(reminder,), daemon=True)
                    self.monitoring_threads[reminder.id] = thread
                    thread.start()

            # Clear input fields
            self.title_entry.delete(0, tk.END)
            self.description_entry.delete("1.0", tk.END)
            self.time_entry.delete(0, tk.END)

            # Refresh list and go back to main screen
            self._refresh_list()
            self._show_screen(self.main_screen)

            # Save reminders to file
            self._save_reminders()

            messagebox.showinfo("Success", "Reminder added successfully!" if not hasattr(self, 'editing_reminder_id') else "Reminder updated successfully!")
        except ValueError:
            messagebox.showerror("Error", "Invalid time format. Use HH:MM (24-hour)")
    def _edit_reminder(self, reminder_id):
        """
        Open the Add Reminder screen with the data of the selected reminder for editing.
        """
        with self.reminders_lock:
            if reminder_id not in self.reminders:
                messagebox.showerror("Error", "Reminder not found.")
                return

            reminder = self.reminders[reminder_id]

        # Set fields with the reminder data
        self.title_entry.delete(0, tk.END)
        self.title_entry.insert(0, reminder.title)

        self.description_entry.delete("1.0", tk.END)
        self.description_entry.insert("1.0", reminder.description)

        self.date_picker.set_date(reminder.trigger_time.strftime("%Y-%m-%d"))
        self.time_entry.delete(0, tk.END)
        self.time_entry.insert(0, reminder.trigger_time.strftime("%H:%M"))

        # Store the reminder ID in an instance variable to indicate edit mode
        self.editing_reminder_id = reminder_id
        

        # Show the Add Reminder screen
        self._show_screen(self.add_screen)
    
    def _refresh_list(self):
        """
        Refresh the reminder list as cards that take the full width of the container.
        """
        print("Refreshing reminder list...")
        try:
            for widget in self.reminder_list.winfo_children():
                widget.destroy()  # Destroy all widgets in the list
        except Exception as e:
            print(f"Error destroying widgets: {e}")  # Log any errors

        with self.reminders_lock:
            for reminder_id, reminder in self.reminders.items():
                print(f"Creating card for reminder ID: {reminder_id}")
                status = "Active" if reminder.is_active else "Expired"

                # Full-width Card Frame
                card_frame = tk.Frame(self.reminder_list, relief=tk.RIDGE, borderwidth=2, padx=10, pady=10, bg="white")
                card_frame.pack(fill=tk.X, padx=10, pady=5)

                # Reminder details
                title_label = tk.Label(card_frame, text=f"Title: {reminder.title}", font=("Arial", 12, "bold"), bg="white")
                title_label.pack(anchor="w", pady=(0, 5))

                description_label = tk.Label(
                    card_frame,
                    text=f"Description: {reminder.description}",
                    wraplength=self.canvas.winfo_width() - 40,
                    bg="white"
                )
                description_label.pack(anchor="w", pady=(0, 5))

                time_label = tk.Label(
                    card_frame,
                    text=f"Time: {reminder.trigger_time.strftime('%Y-%m-%d %H:%M')} ({status})",
                    bg="white"
                )
                time_label.pack(anchor="w", pady=(0, 5))

               # Add a container for the buttons (to group them together)
                button_container = tk.Frame(card_frame, bg="white")
                button_container.pack(anchor="e", pady=(0, 5))

                # Remove button
                remove_button = tk.Button(
                    button_container,
                    text="Remove",
                    image=self.trash_icon,
                    compound="left",
                    command=lambda r_id=reminder_id: self._remove_reminder(r_id),
                    bg="#FF4C4C",
                    fg="white"
                )
                remove_button.pack(side=tk.LEFT, padx=5)

                # Edit button
                edit_button = tk.Button(
                    button_container,
                    text="Edit",
                     image=self.edit_icon,
                    compound="left",
                    command=lambda r_id=reminder_id: self._edit_reminder(r_id),
                    bg="#3797AC",
                    fg="white"
                )
                edit_button.pack(side=tk.LEFT, padx=5)

        # Update the scroll region based on the size of the reminder_list
        self.canvas.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        print("Reminder list refreshed.")


    def _remove_reminder(self, reminder_id):
        """
        Remove a reminder and clean up monitoring thread.
        """
        with self.reminders_lock:
            # Check if reminder exists
            if reminder_id not in self.reminders:
                messagebox.showerror("Error", "Reminder not found or already removed.")
                return

            # Mark reminder as inactive and remove it
            reminder = self.reminders.pop(reminder_id)
            reminder.is_active = False

            # Stop and remove the associated thread
            if reminder_id in self.monitoring_threads:
                print(f"Stopping thread for reminder ID: {reminder_id}")
                del self.monitoring_threads[reminder_id]

            print(f"Reminder {reminder_id} removed successfully.")

        # Save the updated reminders to file
        self._save_reminders()

        # Update UI from the main thread
        self.master.after(0, self._refresh_list)
        messagebox.showinfo("Success", "Reminder removed.")

        
    def _monitor_reminder(self, reminder):
        """
        Monitor a reminder and trigger notification when it's time.
        """
        print(f"Started monitoring thread for reminder ID: {reminder.id}")
        while not self.stop_event.is_set():
            print(f"Started monitoring thread for reminder ID:{self.monitoring_threads[reminder.id]} {reminder.trigger_time}")
            current_time = datetime.now()

            # Check if reminder is inactive
            if not reminder.is_active:
                print(f"Stopping monitoring for reminder ID: {reminder.id}")
                break

            # Trigger notification when the time is due
            if current_time >= reminder.trigger_time and reminder.is_active:
                print(f"Triggering notification for reminder ID: {reminder.id}")
                self.notification_queue.put({"title": reminder.title, "description": reminder.description})

                # Mark the reminder as inactive
                with self.reminders_lock:
                    reminder.is_active = False

                # Update the UI from the main thread
                self.master.after(0, self._refresh_list)
                break

            # Sleep briefly before checking again
            time.sleep(1)

        print(f"Exited monitoring thread for reminder ID: {reminder.id}")

    def _handle_notifications(self):
        """
        Handle and display notifications with an image and custom sound from the queue.
        """
        while not self.stop_event.is_set():
            try:
                notification = self.notification_queue.get(timeout=1)
                print(f"Notification: {notification}")  # Debug: Check the notification data

                # Play the custom sound
                threading.Thread(target=self._play_sound, args=("C:/Users/dell/Desktop/reminder app/notification_sound.wav",), daemon=True).start()

                # Show the notification window with an image
                self.master.after(0, lambda n=notification: self._show_notification(n))
            except queue.Empty:
                continue

    def _play_sound(self, sound_file):
        """
        Play a custom sound using playsound.
        """
        try:
            playsound(sound_file)
        except Exception as e:
            print(f"Error playing sound: {e}")

    def _show_notification(self, notification):
        """
        Display a custom notification window with an image.
        """
        # Create a new top-level window for the notification
        notif_window = tk.Toplevel(self.master)
        notif_window.title("Reminder Alert")
        notif_window.geometry("300x200")
        notif_window.resizable(False, False)

        try:
            # Load and display an image in the notification
            notif_image = ImageTk.PhotoImage(Image.open("bell.png").resize((50, 50)))
            img_label = tk.Label(notif_window, image=notif_image)
            img_label.image = notif_image  # Keep a reference to prevent garbage collection
            img_label.pack(pady=10)
        except Exception as e:
            print(f"Error loading image: {e}")

        # Display notification text
        title_label = tk.Label(notif_window, text=f"Title: {notification['title']}", font=("Arial", 12, "bold"))
        title_label.pack(pady=5)

        desc_label = tk.Label(notif_window, text=f"Description: {notification['description']}", wraplength=250)
        desc_label.pack(pady=5)

        # Add a dismiss button
        dismiss_button = ttk.Button(notif_window, text="Dismiss", command=notif_window.destroy)
        dismiss_button.pack(pady=10)

        # Ensure the notification window stays on top
        notif_window.attributes('-topmost', True)
        notif_window.after(5000, notif_window.destroy)

    def on_closing(self):
        """
        Handle application closing
        """
        self.stop_event.set()
        self.master.destroy()


def main():
    root = tk.Tk()
    app = ReminderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
