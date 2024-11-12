import time
import json
import os
import threading
import sys
import termios
import tty
from datetime import timedelta, datetime

SAVE_FILE = "activity_progress.json"

class Timer:
    def __init__(self, label, remaining_seconds=None, start_time=None):
        self.label = label
        if remaining_seconds is not None:
            self.remaining_seconds = remaining_seconds
        else:
            self.remaining_seconds = 10000 * 3600  # 10,000 hours in seconds
        if start_time is not None:
            self.start_time = start_time
        else:
            self.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.is_paused = True
        self._start_time_internal = None

    def start(self):
        if self.is_paused:
            self.is_paused = False
            self._start_time_internal = time.time()

    def pause(self):
        if not self.is_paused:
            elapsed = time.time() - self._start_time_internal
            self.remaining_seconds -= int(elapsed)
            self.is_paused = True
            self._start_time_internal = None

    def update(self):
        if not self.is_paused and self._start_time_internal:
            elapsed = time.time() - self._start_time_internal
            return self.remaining_seconds - int(elapsed)
        return self.remaining_seconds

    def get_time_remaining(self):
        total_seconds = self.update()
        if total_seconds < 0:
            total_seconds = 0
        return str(timedelta(seconds=total_seconds))

    def save_progress(self):
        data = load_progress()
        data[self.label] = {
            'remaining_seconds': self.update(),
            'start_time': self.start_time
        }
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f)

    def add_time(self, seconds):
        self.remaining_seconds += seconds
        self.save_progress()

def load_progress():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_progress(data):
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f)

def display_menu(progress_data):
    print("\n--- Activity Timer Menu ---")
    print("1. Set new activity (10,000 hours)")
    print("2. Start, resume, stop, or modify an activity")
    print("3. Remove an activity")
    idx = 1
    for label, info in progress_data.items():
        if isinstance(info, dict):
            remaining_seconds = info['remaining_seconds']
            start_time = info['start_time']
        else:
            remaining_seconds = info  # Old format
            start_time = "Unknown"
        hours_remaining = str(timedelta(seconds=remaining_seconds))
        print(f"   {idx}. {label}: {hours_remaining} remaining (Started on: {start_time})")
        idx +=1
    print("4. Exit")
    print("---------------------------")

def handle_timer_activity(timer, progress_data, pause_event):
    try:
        while not timer.is_paused:
            total_seconds = timer.update()
            if total_seconds <= 0:
                print(f"\nActivity '{timer.label}' completed!")
                timer.is_paused = True
                timer.remaining_seconds = 0
                timer.save_progress()
                progress_data[timer.label]['remaining_seconds'] = timer.remaining_seconds
                break
            print(f"\rCounting down for '{timer.label}': {timer.get_time_remaining()} (Press 'p' to pause)", end="")
            time.sleep(1)
            if pause_event.is_set():
                timer.pause()
                timer.save_progress()
                progress_data[timer.label]['remaining_seconds'] = timer.remaining_seconds
                print(f"\nActivity '{timer.label}' paused with {timer.get_time_remaining()} remaining.")
                pause_event.clear()
                break
    except KeyboardInterrupt:
        timer.pause()
        timer.save_progress()
        progress_data[timer.label]['remaining_seconds'] = timer.remaining_seconds
        print(f"\nActivity '{timer.label}' paused with {timer.get_time_remaining()} remaining.")

def get_input(pause_event):
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)  # Set terminal to cbreak mode
        while True:
            ch = sys.stdin.read(1)
            if ch.lower() == 'p':
                pause_event.set()
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)  # Restore terminal settings

def main():
    progress_data = load_progress()
    active_timer = None

    while True:
        display_menu(progress_data)
        choice = input("\nChoose an option: ")

        if choice == "1":
            label = input("Enter the name of the new activity: ")
            if label in progress_data:
                print(f"Activity '{label}' already exists. Choose option 2 to start/resume it.")
            else:
                active_timer = Timer(label)
                progress_data[label] = {
                    'remaining_seconds': active_timer.remaining_seconds,
                    'start_time': active_timer.start_time
                }
                save_progress(progress_data)
                print(f"New activity '{label}' created with 10,000 hours.")

        elif choice == "2":
            if not progress_data:
                print("No activities available. Create a new one first.")
                continue

            try:
                activity_num = int(input("Enter the number of the activity to start/resume/stop or modify: "))
                labels = list(progress_data.keys())
                label = labels[activity_num - 1]
                info = progress_data[label]

                if isinstance(info, dict):
                    remaining_seconds = info['remaining_seconds']
                    start_time = info['start_time']
                else:
                    remaining_seconds = info  # Old format
                    start_time = "Unknown"

                active_timer = Timer(label, remaining_seconds=remaining_seconds, start_time=start_time)

            except (IndexError, ValueError):
                print("Invalid selection. Try again.")
                continue

            sub_choice = input("Enter 's' to start/resume, 'p' to pause/stop, or 'm' to modify time: ").lower()
            if sub_choice == 's':
                if active_timer.is_paused:
                    print(f"Starting or resuming '{label}' with {active_timer.get_time_remaining()} remaining.")
                    active_timer.start()
                    pause_event = threading.Event()
                    timer_thread = threading.Thread(target=handle_timer_activity, args=(active_timer, progress_data, pause_event))
                    input_thread = threading.Thread(target=get_input, args=(pause_event,))
                    timer_thread.start()
                    input_thread.start()
                    timer_thread.join()
                    input_thread.join()
                else:
                    print(f"Activity '{label}' is already running.")

            elif sub_choice == 'p':
                if not active_timer.is_paused:
                    active_timer.pause()
                    active_timer.save_progress()
                    progress_data[label]['remaining_seconds'] = active_timer.remaining_seconds
                    save_progress(progress_data)
                    print(f"Activity '{label}' paused with {active_timer.get_time_remaining()} remaining.")
                else:
                    print(f"Activity '{label}' is already paused.")

            elif sub_choice == 'm':
                try:
                    additional_time = int(input("Enter additional time in seconds to add (use negative numbers to subtract): "))
                    active_timer.add_time(additional_time)
                    progress_data[label]['remaining_seconds'] = active_timer.remaining_seconds
                    save_progress(progress_data)
                    print(f"Updated '{label}'. New time remaining: {active_timer.get_time_remaining()}.")
                except ValueError:
                    print("Invalid time input. Please enter a number.")

        elif choice == "3":
            # Remove an activity
            if not progress_data:
                print("No activities available to remove.")
                continue

            print("Select an activity to remove:")
            idx = 1
            labels = list(progress_data.keys())
            for label in labels:
                print(f"   {idx}. {label}")
                idx += 1

            try:
                activity_num = int(input("Enter the number of the activity to remove: "))
                label = labels[activity_num - 1]
                confirm = input(f"Are you sure you want to remove '{label}'? (y/n): ").lower()
                if confirm == 'y':
                    del progress_data[label]
                    save_progress(progress_data)
                    print(f"Activity '{label}' has been removed.")
                else:
                    print("Removal cancelled.")
            except (IndexError, ValueError):
                print("Invalid selection. Try again.")
                continue

        elif choice == "4":
            if active_timer and not active_timer.is_paused:
                active_timer.pause()
                active_timer.save_progress()
                progress_data[active_timer.label]['remaining_seconds'] = active_timer.remaining_seconds
                save_progress(progress_data)
                print(f"Exiting. Progress saved for '{active_timer.label}' with {active_timer.get_time_remaining()} remaining.")
            else:
                print("Exiting.")
            break
        else:
            print("Invalid option. Please try again.")

if __name__ == "__main__":
    main()

