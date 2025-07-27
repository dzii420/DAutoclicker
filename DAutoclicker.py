import pyautogui
import time
import random
import datetime
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json # For saving and loading settings
import webbrowser # New import for opening hyperlinks
import tkinter.font as tkFont # New import for custom fonts

# --- Configuration Variables (Default Values) ---
# Interval settings (in milliseconds)
DEFAULT_MIN_INTERVAL_MS = 5000  # 5 seconds
DEFAULT_MAX_INTERVAL_MS = 10000 # 10 seconds

# Pause schedule (24-hour format H:M)
DEFAULT_PAUSE_START_TIME_STR = "23:45" # 11:45 PM
DEFAULT_PAUSE_END_TIME_STR = "06:00"   # 6 AM

# Click position (X, Y coordinates on screen for 'defined_coordinates' mode)
CLICK_X = 161 # Default X coordinate
CLICK_Y = 992 # Default Y coordinate

# Default click settings
DEFAULT_MOUSE_BUTTON = "left" # "left", "right", "middle"
DEFAULT_CLICK_TYPE = "single" # "single", "double"
DEFAULT_CLICK_REPEAT_MODE = "infinite" # "infinite", "limited"
DEFAULT_CLICK_LIMIT = 500 # Default number of clicks if limited

# Click Mode and Area Coordinates
DEFAULT_CLICK_LOCATION_MODE = "current_mouse_location" # "current_mouse_location", "defined_coordinates", "random_area"
AREA_X1, AREA_Y1, AREA_X2, AREA_Y2 = 0, 0, 1920, 1080 # Default full screen area

# --- Global State ---
is_running = False
autoclick_thread = None
next_click_timestamp = 0 # Unix timestamp (float) for the next click
countdown_update_id = None # Stores the ID for the Tkinter after() call for countdown
current_clicks = 0 # Counter for limited clicks

# --- GUI Elements (references to Tkinter widgets) ---
root = None
min_h_var, min_m_var, min_s_var, min_ms_var = None, None, None, None
max_h_var, max_m_var, max_s_var, max_ms_var = None, None, None, None
pause_start_var, pause_end_var = None, None
coord_x_label, coord_y_label = None, None
status_label = None
countdown_label = None
made_by_label = None # New global reference for the "Made by" label
github_link_label = None # New global reference for the GitHub link label
start_button = None
stop_button = None
set_fixed_coords_button = None # Renamed from record_button
always_on_top_var = None
override_sleep_var = None
mouse_button_var = None
click_type_var = None
click_repeat_mode_var = None
click_limit_var = None
click_limit_entry = None
click_location_mode_var = None # Renamed from click_mode_var
fixed_coords_subframe = None # Frame for defined coordinates controls
random_area_subframe = None # Frame for random area controls
current_mouse_location_subframe = None # Frame for current mouse location info
area_x1_label, area_y1_label, area_x2_label, area_y2_label = None, None, None, None
draw_area_button = None # Reference to the draw area button

# Variables for area selection drawing
selection_window = None
selection_canvas = None
rect_id = None
start_x_select, start_y_select = None, None

# --- Helper Functions ---

def parse_time_str(time_str):
    """Parses a 'HH:MM' string into (hour, minute) tuple."""
    try:
        h, m = map(int, time_str.split(':'))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("Invalid hour or minute value.")
        return h, m
    except ValueError:
        return None, None # Return None for invalid input

def time_to_milliseconds(h, m, s, ms):
    """Converts hours, minutes, seconds, and milliseconds into total milliseconds."""
    return (h * 3600 + m * 60 + s) * 1000 + ms

def milliseconds_to_hmsms(total_ms):
    """Converts total milliseconds back to (hours, minutes, seconds, milliseconds)."""
    total_seconds = total_ms // 1000
    ms = total_ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return int(hours), int(minutes), int(seconds), int(ms)

def get_random_interval():
    """Calculates a random interval in milliseconds based on user input from GUI."""
    try:
        min_h = min_h_var.get()
        min_m = min_m_var.get()
        min_s = min_s_var.get()
        min_ms = min_ms_var.get()
        max_h = max_h_var.get()
        max_m = max_m_var.get()
        max_s = max_s_var.get()
        max_ms = max_ms_var.get()

        min_total_ms = time_to_milliseconds(min_h, min_m, min_s, min_ms)
        max_total_ms = time_to_milliseconds(max_h, max_m, max_s, max_ms)

        if min_total_ms > max_total_ms:
            messagebox.showerror("Input Error", "Minimum interval cannot be greater than maximum interval. Please correct your input.")
            return 0
        if min_total_ms == 0 and max_total_ms == 0:
            messagebox.showerror("Input Error", "Interval cannot be zero. Please set a valid time range.")
            return 0

        # random.uniform works with floats, so we can directly use milliseconds
        return random.uniform(min_total_ms, max_total_ms)
    except tk.TclError: # Handle cases where entry fields might be empty or non-numeric
        messagebox.showerror("Input Error", "Please enter valid numbers for time intervals.")
        return 0

def is_in_pause_time():
    """
    Checks if the current system time falls within the defined pause range.
    Uses values from GUI input fields.
    """
    # If override is active, always return False (not in pause)
    if override_sleep_var.get():
        return False

    now = datetime.datetime.now()
    current_time_minutes = now.hour * 60 + now.minute

    pause_start_h, pause_start_m = parse_time_str(pause_start_var.get())
    pause_end_h, pause_end_m = parse_time_str(pause_end_var.get())

    if pause_start_h is None or pause_end_h is None:
        return False # Treat as not in pause if times are invalid

    pause_start_minutes = pause_start_h * 60 + pause_start_m
    pause_end_minutes = pause_end_h * 60 + pause_end_m

    if pause_start_minutes < pause_end_minutes:
        # Pause time is within the same day (e.g., 09:00 to 17:00)
        return pause_start_minutes <= current_time_minutes < pause_end_minutes
    else:
        # Pause time spans across midnight (e.g., 21:00 to 08:00)
        return current_time_minutes >= pause_start_minutes or current_time_minutes < pause_end_minutes

def perform_click():
    """Simulates a click based on configured mouse button and click type."""
    global CLICK_X, CLICK_Y, current_clicks, is_running, AREA_X1, AREA_Y1, AREA_X2, AREA_Y2

    target_x, target_y = None, None

    if click_location_mode_var.get() == "current_mouse_location":
        # Get current mouse position dynamically
        target_x, target_y = pyautogui.position()
        update_status(f"Clicked at current mouse location: X:{target_x}, Y:{target_y}", "blue")
    elif click_location_mode_var.get() == "defined_coordinates":
        if CLICK_X is None or CLICK_Y is None:
            update_status("Error: Fixed click position not set. Please record a position.", "red")
            stop_autoclicker()
            return
        target_x, target_y = CLICK_X, CLICK_Y
    elif click_location_mode_var.get() == "random_area":
        if not (AREA_X1 is not None and AREA_Y1 is not None and AREA_X2 is not None and AREA_Y2 is not None):
            update_status("Error: Random area not defined. Please draw an area.", "red")
            stop_autoclicker()
            return
        
        # Ensure coordinates are ordered min to max for random.randint
        min_x = min(AREA_X1, AREA_X2)
        max_x = max(AREA_X1, AREA_X2)
        min_y = min(AREA_Y1, AREA_Y2)
        max_y = max(AREA_Y1, AREA_Y2)

        # Handle cases where area is a single line or point (min == max)
        if min_x == max_x:
            target_x = min_x
        else:
            target_x = random.randint(min_x, max_x)
        
        if min_y == max_y:
            target_y = min_y
        else:
            target_y = random.randint(min_y, max_y)
        
        update_status(f"Clicking randomly in area [{min_x},{min_y}] to [{max_x},{max_y}]", "blue")
    
    if target_x is None or target_y is None:
        update_status("Error: Invalid click target. Stopping autoclicker.", "red")
        stop_autoclicker()
        return

    # Debugging print for click type
    print(f"DEBUG: Click type selected: {click_type_var.get()}")

    # Check click repeat limit
    if click_repeat_mode_var.get() == "limited":
        if current_clicks <= 0:
            update_status("Click limit reached. Stopping autoclicker.", "red")
            stop_autoclicker()
            return
        current_clicks -= 1
        # Update status to show remaining clicks
        update_status(f"Clicked at X: {target_x}, Y: {target_y} ({current_clicks} remaining) at {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}", "green")
    else: # Infinite clicks
        update_status(f"Clicked at X: {target_x}, Y: {target_y} at {datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]}", "green")


    try:
        if click_type_var.get() == "single":
            pyautogui.click(target_x, target_y, button=mouse_button_var.get())
        elif click_type_var.get() == "double":
            pyautogui.doubleClick(target_x, target_y, button=mouse_button_var.get())
        else: # Fallback for unexpected value
            print(f"WARNING: Unknown click type '{click_type_var.get()}'. Performing single click.")
            pyautogui.click(target_x, target_y, button=mouse_button_var.get())
        time.sleep(0.01) # Small delay after click for robustness

    except pyautogui.FailSafeException:
        update_status("PyAutoGUI Fail-Safe triggered. Mouse moved to corner. Stopping autoclicker.", "red")
        stop_autoclicker()
    except Exception as e:
        update_status(f"Error during click: {e}. Stopping autoclicker.", "red")
        stop_autoclicker()

def update_status(message, color="black"):
    """Updates the status label in the GUI."""
    if root:
        root.after(0, lambda: [status_label.config(text=message, foreground=color), root.update_idletasks()])

def update_countdown_display():
    """Updates the countdown label in the GUI."""
    global countdown_update_id

    # Safely cancel any pending update
    if countdown_update_id is not None:
        try:
            root.after_cancel(countdown_update_id)
        except tk.TclError:
            # Handle case where ID might have already been cancelled or is invalid
            pass
        countdown_update_id = None # Always clear the ID after attempting to cancel

    if not is_running:
        countdown_label.config(text="Next click in: --:--:--.--")
        root.update_idletasks() # Force update
        return

    remaining_ms = max(0, int((next_click_timestamp - time.time()) * 1000))
    hours, minutes, seconds, ms = milliseconds_to_hmsms(remaining_ms)

    countdown_label.config(text=f"Next click in: {hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}")
    root.update_idletasks() # Force update to ensure the label is redrawn

    if remaining_ms > 0:
        # Only schedule the next update if the app is still running
        if is_running:
            countdown_update_id = root.after(100, update_countdown_display)
    else:
        countdown_label.config(text="Clicking now...")
        root.update_idletasks() # Force update
        countdown_update_id = None # Ensure it's None when countdown finishes

def autoclicker_loop():
    """Main loop for the autoclicker, runs in a separate thread."""
    global is_running, next_click_timestamp

    update_status("Autoclicker thread started.", "blue")

    while is_running:
        if is_in_pause_time():
            update_status(f"Autoclicker paused (sleep schedule: {pause_start_var.get()} to {pause_end_var.get()}).", "orange")
            root.after(0, lambda: countdown_label.config(text="Paused (Sleep Schedule)"))
            time.sleep(60) # Check every minute if still in pause time
            continue

        # Check click limit before scheduling next click
        if click_repeat_mode_var.get() == "limited" and current_clicks <= 0:
            root.after(0, stop_autoclicker)
            break

        interval_ms = get_random_interval()
        if interval_ms == 0: # Error in interval calculation, stop
            root.after(0, stop_autoclicker) # Call stop in main thread
            break

        interval_seconds = interval_ms / 1000.0
        next_click_timestamp = time.time() + interval_seconds
        update_status(f"Autoclicker running. Next click scheduled in {interval_seconds:.3f} seconds.", "blue")
        # Ensure the countdown starts/restarts immediately when a new interval is set
        root.after(0, update_countdown_display) 

        # Wait for the interval, but check is_running periodically
        start_wait_time = time.time()
        while time.time() - start_wait_time < interval_seconds and is_running and not is_in_pause_time():
            time.sleep(0.05) # Smaller sleep for more responsiveness with milliseconds

        if is_running and not is_in_pause_time(): # Ensure still running and not paused before clicking
            perform_click()
        else:
            update_status("Click skipped due to pause or stop.", "gray")

    update_status("Autoclicker thread stopped.", "gray")

def start_autoclicker():
    """Starts the autoclicker process."""
    global is_running, autoclick_thread, current_clicks

    # Validate click position/area based on selected mode
    if click_location_mode_var.get() == "defined_coordinates" and (CLICK_X is None or CLICK_Y is None):
        messagebox.showwarning("Click Position Not Set", "Please record a fixed click position before starting the autoclicker.")
        return
    elif click_location_mode_var.get() == "random_area" and \
         not (AREA_X1 is not None and AREA_Y1 is not None and AREA_X2 is not None and AREA_Y2 is not None and
              (AREA_X1 != AREA_X2 or AREA_Y1 != AREA_Y2)): # Ensure it's not a single point/line
        messagebox.showwarning("Click Area Not Set", "Please draw a valid random click area before starting the autoclicker.")
        return

    if not is_running:
        is_running = True
        # Initialize click counter if in limited mode
        if click_repeat_mode_var.get() == "limited":
            try:
                limit = int(click_limit_var.get())
                if limit <= 0:
                    messagebox.showerror("Input Error", "Click limit must be a positive integer.")
                    is_running = False # Prevent starting if invalid limit
                    return
                current_clicks = limit
            except ValueError:
                messagebox.showerror("Input Error", "Please enter a valid number for click limit.")
                is_running = False # Prevent starting if invalid limit
                return
        else:
            current_clicks = -1 # Indicate infinite clicks

        autoclick_thread = threading.Thread(target=autoclicker_loop, daemon=True)
        autoclick_thread.start()
        start_button.config(state=tk.DISABLED)
        stop_button.config(state=tk.NORMAL)
        set_fixed_coords_button.config(state=tk.DISABLED) # Disable fixed point record button
        draw_area_button.config(state=tk.DISABLED) # Disable draw area button
        update_status("Autoclicker started!", "green")
        # The initial call to update_countdown_display is now handled within autoclicker_loop
    else:
        update_status("Autoclicker is already running.", "orange")

def stop_autoclicker():
    """Stops the autoclicker process."""
    global is_running, autoclick_thread, countdown_update_id
    if is_running:
        is_running = False
        if autoclick_thread and autoclick_thread.is_alive():
            # Give the thread a moment to finish its current loop iteration
            pass
        start_button.config(state=tk.NORMAL)
        stop_button.config(state=tk.DISABLED)
        set_fixed_coords_button.config(state=tk.NORMAL) # Enable fixed point record button
        draw_area_button.config(state=tk.NORMAL) # Enable draw area button
        update_status("Autoclicker stopped.", "red")
        # Ensure any active countdown is cancelled and reset
        if countdown_update_id:
            try:
                root.after_cancel(countdown_update_id)
            except tk.TclError:
                pass # Already cancelled or invalid
            countdown_update_id = None
        countdown_label.config(text="Next click in: --:--:--.--")
        root.update_idletasks() # Force update
    else:
        update_status("Autoclicker is not running.", "gray")

def record_fixed_point_position():
    """Initiates the process to record fixed click coordinates by clicking."""
    # Temporarily disable the button to prevent multiple clicks
    set_fixed_coords_button.config(state=tk.DISABLED)
    update_status("Move mouse to desired location and click. Capturing in 2 seconds...", "blue")

    def capture_coords_thread():
        global CLICK_X, CLICK_Y
        
        # Show the info box from the main thread via root.after
        root.after(0, lambda: messagebox.showinfo("Record Position", "Move your mouse to the desired location and click. The autoclicker window will temporarily hide and reappear after 2 seconds."))
        
        time.sleep(0.1) 

        # Hide the window. This must be called from the main Tkinter thread.
        root.after(0, root.withdraw)
        
        time.sleep(2) # Give 2 seconds for the user to position mouse and click

        try:
            x, y = pyautogui.position() 
            CLICK_X = x
            CLICK_Y = y
            
            # Restore the window and update GUI elements in the main thread
            root.after(0, lambda: [
                root.deiconify(), # Restore the window
                coord_x_label.config(text=f"{CLICK_X}"), 
                coord_y_label.config(text=f"{CLICK_Y}"),
                update_status(f"Fixed click position recorded: X={CLICK_X}, Y={CLICK_Y}", "green"),
                set_fixed_coords_button.config(state=tk.NORMAL) # Re-enable button
            ])
        except Exception as e:
            root.after(0, lambda error_msg=e: [ # Capture 'e' as 'error_msg'
                root.deiconify(), # Restore the window even on error
                update_status(f"Error recording position: {error_msg}", "red"), # Use captured variable
                set_fixed_coords_button.config(state=tk.NORMAL) # Re-enable button
            ])

    threading.Thread(target=capture_coords_thread, daemon=True).start()

def record_click_position_f6():
    """Function to be called when F6 is pressed to record fixed position."""
    global CLICK_X, CLICK_Y
    if click_location_mode_var.get() == "defined_coordinates": # Check if the correct mode is selected
        try:
            x, y = pyautogui.position()
            CLICK_X = x
            CLICK_Y = y
            root.after(0, lambda: [coord_x_label.config(text=f"{CLICK_X}"), coord_y_label.config(text=f"{CLICK_Y}")])
            update_status(f"Fixed click position recorded (F6): X={CLICK_X}, Y={CLICK_Y}", "green")
        except Exception as e:
            update_status(f"Error recording position (F6): {e}", "red")
    else:
        update_status("F6 hotkey is for 'Set Fixed Coordinates' mode only. Change click mode to use.", "orange")


def start_area_selection():
    """Initiates the process to draw a random click area on screen."""
    global selection_window, selection_canvas, rect_id, start_x_select, start_y_select

    # Disable buttons during selection
    draw_area_button.config(state=tk.DISABLED)
    set_fixed_coords_button.config(state=tk.DISABLED)

    # Hide main window
    root.withdraw()
    time.sleep(0.1) # Give Tkinter time to process window hiding

    # Create a transparent fullscreen window for selection
    selection_window = tk.Toplevel(root)
    selection_window.overrideredirect(True) # Remove window decorations
    selection_window.attributes('-alpha', 0.3) # Transparency
    selection_window.attributes('-topmost', True) # Always on top

    # Get screen dimensions
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    selection_window.geometry(f"{screen_width}x{screen_height}+0+0")

    selection_canvas = tk.Canvas(selection_window, bg='grey', highlightthickness=0)
    selection_canvas.pack(fill=tk.BOTH, expand=True)

    # Grab focus and set grab to ensure all events go to this window
    selection_window.grab_set()
    selection_window.focus_set()

    # Bind mouse events to the canvas
    selection_canvas.bind("<ButtonPress-1>", on_button_press)
    selection_canvas.bind("<B1-Motion>", on_mouse_drag)
    selection_canvas.bind("<ButtonRelease-1>", on_button_release)

    update_status("Draw a rectangle on screen by dragging your mouse.", "blue")

def on_button_press(event):
    """Records the starting coordinates for drawing the selection rectangle."""
    global start_x_select, start_y_select, rect_id
    start_x_select = event.x_root
    start_y_select = event.y_root
    print(f"DEBUG: Area selection started at: ({start_x_select}, {start_y_select})") # Debug print
    # Delete previous rectangle if exists
    if rect_id:
        selection_canvas.delete(rect_id)
    rect_id = selection_canvas.create_rectangle(start_x_select, start_y_select, start_x_select, start_y_select,
                                                outline='red', width=2, dash=(5, 2))

def on_mouse_drag(event):
    """Updates the drawn rectangle as the mouse is dragged."""
    global rect_id
    if rect_id:
        selection_canvas.coords(rect_id, start_x_select, start_y_select, event.x_root, event.y_root)

def on_button_release(event):
    """Records the final coordinates and updates the main GUI with the selected area."""
    global AREA_X1, AREA_Y1, AREA_X2, AREA_Y2, selection_window, selection_canvas, rect_id, start_x_select, start_y_select

    try:
        end_x_select = event.x_root
        end_y_select = event.y_root
        print(f"DEBUG: Area selection ended at: ({end_x_select}, {end_y_select})") # Debug print

        # Store coordinates in a normalized way (top-left, bottom-right)
        # Ensure start_x_select and start_y_select are not None
        if start_x_select is None or start_y_select is None:
            raise ValueError("Start coordinates for area selection were not set.")

        AREA_X1 = min(start_x_select, end_x_select)
        AREA_Y1 = min(start_y_select, end_y_select)
        AREA_X2 = max(start_x_select, end_x_select)
        AREA_Y2 = max(start_y_select, end_y_select)
        print(f"DEBUG: Calculated Area: X1={AREA_X1}, Y1={AREA_Y1}, X2={AREA_X2}, Y2={AREA_Y2}") # Debug print

        # Update labels in main GUI
        root.after(0, lambda: [
            area_x1_label.config(text=f"{AREA_X1}"),
            area_y1_label.config(text=f"{AREA_Y1}"),
            area_x2_label.config(text=f"{AREA_X2}"),
            area_y2_label.config(text=f"{AREA_Y2}"),
            update_status(f"Random area recorded: [{AREA_X1},{AREA_Y1}] to [{AREA_X2},{AREA_Y2}]", "green"),
            area_coords_frame.update_idletasks() # Explicitly update this frame
        ])

    except Exception as e:
        # Pass the exception message to the lambda function
        root.after(0, lambda error_msg=str(e): update_status(f"Error during area selection: {error_msg}", "red"))
    finally:
        # Ensure grab is released and window is restored even on error
        if selection_window:
            selection_window.grab_release()
            selection_window.destroy()
            selection_window = None
        selection_canvas = None
        rect_id = None
        start_x_select, start_y_select = None, None # Reset these global variables

        time.sleep(0.1) # Give Tkinter time to process window destruction
        root.deiconify() # Restore the main window
        root.update_idletasks() # Ensure window is fully rendered
        set_fixed_coords_button.config(state=tk.NORMAL) # Re-enable fixed point record button
        draw_area_button.config(state=tk.NORMAL) # Re-enable draw area button


def toggle_always_on_top():
    """Toggles the 'always on top' attribute of the main window."""
    root.attributes("-topmost", always_on_top_var.get())

def toggle_click_limit_entry_state():
    """Enables/disables the click limit entry based on radio button selection."""
    if click_repeat_mode_var.get() == "limited":
        click_limit_entry.config(state=tk.NORMAL)
    else:
        click_limit_entry.config(state=tk.DISABLED)

def toggle_click_mode_controls():
    """Shows/hides controls based on selected click mode."""
    # Hide all subframes first
    fixed_coords_subframe.pack_forget()
    random_area_subframe.pack_forget()
    current_mouse_location_subframe.pack_forget()
    made_by_label.pack_forget() # Hide the "Made by" label by default
    github_link_label.pack_forget() # Hide GitHub link by default

    # Show the relevant subframe
    if click_location_mode_var.get() == "defined_coordinates":
        fixed_coords_subframe.pack(fill=tk.X, pady=2)
    elif click_location_mode_var.get() == "random_area":
        random_area_subframe.pack(fill=tk.X, pady=2)
    elif click_location_mode_var.get() == "current_mouse_location":
        current_mouse_location_subframe.pack(fill=tk.X, pady=2)
        made_by_label.pack(fill=tk.X, pady=2, anchor="center") # Show "Made by" label only for this mode, centered
        github_link_label.pack(fill=tk.X, pady=1, anchor="center") # Show GitHub link, centered, small pady

def save_settings():
    """Saves current GUI settings to a JSON file."""
    global CLICK_X, CLICK_Y, AREA_X1, AREA_Y1, AREA_X2, AREA_Y2
    settings = {
        "min_h": min_h_var.get(),
        "min_m": min_m_var.get(),
        "min_s": min_s_var.get(),
        "min_ms": min_ms_var.get(),
        "max_h": max_h_var.get(),
        "max_m": max_m_var.get(),
        "max_s": max_s_var.get(),
        "max_ms": max_ms_var.get(),
        "pause_start": pause_start_var.get(),
        "pause_end": pause_end_var.get(),
        "click_x": CLICK_X,
        "click_y": CLICK_Y,
        "always_on_top": always_on_top_var.get(),
        "override_sleep": override_sleep_var.get(),
        "mouse_button": mouse_button_var.get(),
        "click_type": click_type_var.get(),
        "click_repeat_mode": click_repeat_mode_var.get(),
        "click_limit": click_limit_var.get() if click_repeat_mode_var.get() == "limited" else None,
        "click_location_mode": click_location_mode_var.get(), # Renamed setting
        "area_x1": AREA_X1,
        "area_y1": AREA_Y1,
        "area_x2": AREA_X2,
        "area_y2": AREA_Y2
    }
    file_path = filedialog.asksaveasfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Save Settings As"
    )
    if file_path:
        try:
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=4)
            update_status(f"Settings saved to {file_path}", "green")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save settings: {e}")
            update_status("Failed to save settings.", "red")

def load_settings():
    """Loads settings from a JSON file and applies them to the GUI."""
    global CLICK_X, CLICK_Y, AREA_X1, AREA_Y1, AREA_X2, AREA_Y2
    file_path = filedialog.askopenfilename(
        defaultextension=".json",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        title="Load Settings From"
    )
    if file_path:
        try:
            with open(file_path, 'r') as f:
                settings = json.load(f)
            
            # Apply loaded settings to GUI variables
            min_h_var.set(settings.get("min_h", 0))
            min_m_var.set(settings.get("min_m", 0))
            min_s_var.set(settings.get("min_s", 0))
            min_ms_var.set(settings.get("min_ms", 0))
            max_h_var.set(settings.get("max_h", 0))
            max_m_var.set(settings.get("max_m", 0))
            max_s_var.set(settings.get("max_s", 0))
            max_ms_var.set(settings.get("max_ms", 0))
            pause_start_var.set(settings.get("pause_start", "00:00"))
            pause_end_var.set(settings.get("pause_end", "00:00"))
            
            CLICK_X = settings.get("click_x")
            CLICK_Y = settings.get("click_y")
            coord_x_label.config(text=f"{CLICK_X}" if CLICK_X is not None else "N/A")
            coord_y_label.config(text=f"{CLICK_Y}" if CLICK_Y is not None else "N/A")

            always_on_top_var.set(settings.get("always_on_top", False))
            toggle_always_on_top() # Apply the setting
            override_sleep_var.set(settings.get("override_sleep", False))
            
            # New settings
            mouse_button_var.set(settings.get("mouse_button", DEFAULT_MOUSE_BUTTON))
            click_type_var.set(settings.get("click_type", DEFAULT_CLICK_TYPE))
            click_repeat_mode_var.set(settings.get("click_repeat_mode", DEFAULT_CLICK_REPEAT_MODE))
            click_limit_var.set(settings.get("click_limit", DEFAULT_CLICK_LIMIT))
            toggle_click_limit_entry_state() # Update state of limit entry

            click_location_mode_var.set(settings.get("click_location_mode", DEFAULT_CLICK_LOCATION_MODE)) # Renamed setting
            toggle_click_mode_controls() # Update visibility of click mode controls

            AREA_X1 = settings.get("area_x1", 0)
            AREA_Y1 = settings.get("area_y1", 0)
            AREA_X2 = settings.get("area_x2", 0)
            AREA_Y2 = settings.get("area_y2", 0)
            area_x1_label.config(text=f"{AREA_X1}")
            area_y1_label.config(text=f"{AREA_Y1}")
            area_x2_label.config(text=f"{AREA_X2}")
            area_y2_label.config(text=f"{AREA_Y2}")


            update_status(f"Settings loaded from {file_path}", "green")
        except json.JSONDecodeError:
            messagebox.showerror("Load Error", "Invalid JSON file format.")
            update_status("Failed to load settings: Invalid file.", "red")
        except FileNotFoundError:
            messagebox.showerror("Load Error", "File not found.")
            update_status("Failed to load settings: File not found.", "red")
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load settings: {e}")
            update_status("Failed to load settings.", "red")

def on_closing():
    """Handles proper shutdown when the GUI window is closed."""
    stop_autoclicker() # Ensure the autoclicker thread is stopped
    root.destroy()
    sys.exit() # Exit the Python script

def create_gui():
    """Creates and sets up the Tkinter GUI."""
    global root, min_h_var, min_m_var, min_s_var, min_ms_var, \
           max_h_var, max_m_var, max_s_var, max_ms_var, \
           pause_start_var, pause_end_var, \
           coord_x_label, coord_y_label, \
           status_label, countdown_label, made_by_label, github_link_label, \
           start_button, stop_button, set_fixed_coords_button, always_on_top_var, \
           override_sleep_var, mouse_button_var, click_type_var, \
           click_repeat_mode_var, click_limit_var, click_limit_entry, \
           click_location_mode_var, fixed_coords_subframe, random_area_subframe, \
           current_mouse_location_subframe, \
           area_x1_label, area_y1_label, area_x2_label, area_y2_label, \
           draw_area_button

    root = tk.Tk()
    root.title("DAutoclicker") # Changed title here
    root.geometry("500x816") # Shortened height by 17 pixels
    root.resizable(False, False) # Fixed size for simplicity

    # --- Icon (Platform-specific, uncomment and provide path to your .ico file) ---
    try:
        # Use the absolute path provided by the user for the icon
        root.iconbitmap('C:\\bot\\icon.ico') 
    except tk.TclError:
        # Handle cases where the .ico file is not found or platform doesn't support it
        print("Warning: Could not load icon. Ensure 'C:\\bot\\icon.ico' is correct and the file exists.")
        pass

    # Configure style
    style = ttk.Style()
    style.theme_use('clam') # 'clam', 'alt', 'default', 'classic'

    # General background for the root window
    root.configure(background='#e8f0f7') # Light blue-gray

    # Frame styles
    style.configure('TFrame', background='#e8f0f7')
    style.configure('TLabelframe', background='#e8f0f7', foreground='#334155', font=('Segoe UI', 10, 'bold')) # Smaller font
    style.configure('TLabelframe.Label', background='#e8f0f7', foreground='#334155') # Label within LabelFrame

    # Label styles
    style.configure('TLabel', background='#e8f0f7', font=('Segoe UI', 8), foreground='#475569') # Slightly smaller font
    style.configure('Status.TLabel', font=('Segoe UI', 8, 'bold'), anchor='center') # Slightly smaller font
    style.configure('Countdown.TLabel', font=('Segoe UI', 12, 'bold'), anchor='center', # Slightly smaller font
                    background='#d0e6ff', foreground='#1a4a8a', relief='raised', borderwidth=2) # More prominent countdown
    
    # Custom font for the GitHub link to enable underline
    github_font = tkFont.Font(family="Segoe UI", size=12, underline=1)
    style.configure('MadeBy.TLabel', background='#e8f0f7', font=('Segoe UI', 12, 'italic'), foreground='#64748b', anchor='center')


    # Button styles
    style.configure('TButton', font=('Segoe UI', 8, 'bold'), padding=6, relief='raised', borderwidth=1) # Slightly smaller padding/font
    style.map('TButton',
              background=[('active', '#e0e0e0'), ('!disabled', '#f0f0f0')],
              foreground=[('active', 'black'), ('!disabled', '#333333')])

    style.configure('Accent.TButton', background='#007bff', foreground='white', relief='raised', borderwidth=1)
    style.map('Accent.TButton',
              background=[('active', '#0056b3'), ('!disabled', '#007bff')],
              foreground=[('active', 'white'), ('!disabled', 'white')])

    # Entry and Spinbox styles
    style.configure('TEntry', padding=3, fieldbackground='white', foreground='#1e293b') # Slightly smaller padding
    style.configure('TSpinbox', padding=3, fieldbackground='white', foreground='#1e293b') # Slightly smaller padding

    # Checkbutton style
    style.configure('TCheckbutton', background='#e8f0f7', font=('Segoe UI', 8), foreground='#475569') # Slightly smaller font
    style.configure('TRadiobutton', background='#e8f0f7', font=('Segoe UI', 8), foreground='#475569') # Radiobutton style


    main_frame = ttk.Frame(root, padding="10 10 10 10") # Reduced main padding
    main_frame.pack(fill=tk.BOTH, expand=True)

    # --- Interval Settings ---
    interval_frame = ttk.LabelFrame(main_frame, text="Click Interval Range (H:M:S.ms)", padding="8 8 8 8") # Reduced padding
    interval_frame.pack(fill=tk.X, pady=5) # Reduced pady

    # Min Interval
    min_h, min_m, min_s, min_ms = milliseconds_to_hmsms(DEFAULT_MIN_INTERVAL_MS)
    min_h_var = tk.IntVar(value=min_h)
    min_m_var = tk.IntVar(value=min_m)
    min_s_var = tk.IntVar(value=min_s)
    min_ms_var = tk.IntVar(value=min_ms) # New milliseconds variable

    ttk.Label(interval_frame, text="Min:").grid(row=0, column=0, padx=3, pady=2, sticky="w") # Reduced padx/pady
    ttk.Spinbox(interval_frame, from_=0, to=23, textvariable=min_h_var, width=3).grid(row=0, column=1, padx=1, pady=2) # Smaller width, reduced pady
    ttk.Label(interval_frame, text="H").grid(row=0, column=2, sticky="w")
    ttk.Spinbox(interval_frame, from_=0, to=59, textvariable=min_m_var, width=3).grid(row=0, column=3, padx=1, pady=2) # Smaller width, reduced pady
    ttk.Label(interval_frame, text="M").grid(row=0, column=4, sticky="w")
    ttk.Spinbox(interval_frame, from_=0, to=59, textvariable=min_s_var, width=3).grid(row=0, column=5, padx=1, pady=2) # Smaller width, reduced pady
    ttk.Label(interval_frame, text="S").grid(row=0, column=6, sticky="w")
    ttk.Spinbox(interval_frame, from_=0, to=999, textvariable=min_ms_var, width=4).grid(row=0, column=7, padx=1, pady=2) # New MS input, reduced pady
    ttk.Label(interval_frame, text="ms").grid(row=0, column=8, sticky="w")

    # Max Interval
    max_h, max_m, max_s, max_ms = milliseconds_to_hmsms(DEFAULT_MAX_INTERVAL_MS)
    max_h_var = tk.IntVar(value=max_h)
    max_m_var = tk.IntVar(value=max_m)
    max_s_var = tk.IntVar(value=max_s)
    max_ms_var = tk.IntVar(value=max_ms) # New milliseconds variable

    ttk.Label(interval_frame, text="Max:").grid(row=1, column=0, padx=3, pady=2, sticky="w") # Reduced padx/pady
    ttk.Spinbox(interval_frame, from_=0, to=23, textvariable=max_h_var, width=3).grid(row=1, column=1, padx=1, pady=2) # Smaller width, reduced pady
    ttk.Label(interval_frame, text="H").grid(row=1, column=2, sticky="w")
    ttk.Spinbox(interval_frame, from_=0, to=59, textvariable=max_m_var, width=3).grid(row=1, column=3, padx=1, pady=2) # Smaller width, reduced pady
    ttk.Label(interval_frame, text="M").grid(row=1, column=4, sticky="w")
    ttk.Spinbox(interval_frame, from_=0, to=59, textvariable=max_s_var, width=3).grid(row=1, column=5, padx=1, pady=2) # Smaller width, reduced pady
    ttk.Label(interval_frame, text="S").grid(row=1, column=6, sticky="w")
    ttk.Spinbox(interval_frame, from_=0, to=999, textvariable=max_ms_var, width=4).grid(row=1, column=7, padx=1, pady=2) # New MS input, reduced pady
    ttk.Label(interval_frame, text="ms").grid(row=1, column=8, sticky="w")
    
    # Make columns expand evenly (adjusted for new columns)
    for i in range(9):
        interval_frame.grid_columnconfigure(i, weight=1)


    # --- Pause Schedule ---
    pause_frame = ttk.LabelFrame(main_frame, text="Pause Schedule (24h HH:MM)", padding="8 8 8 8") # Reduced padding
    pause_frame.pack(fill=tk.X, pady=5) # Reduced pady

    pause_start_var = tk.StringVar(value=DEFAULT_PAUSE_START_TIME_STR)
    pause_end_var = tk.StringVar(value=DEFAULT_PAUSE_END_TIME_STR)

    ttk.Label(pause_frame, text="Pause From:").grid(row=0, column=0, padx=5, pady=2, sticky="w") # Reduced pady
    ttk.Entry(pause_frame, textvariable=pause_start_var, width=10).grid(row=0, column=1, padx=5, pady=2, sticky="ew") # Reduced pady
    ttk.Label(pause_frame, text="Resume At:").grid(row=1, column=0, padx=5, pady=2, sticky="w") # Reduced pady
    ttk.Entry(pause_frame, textvariable=pause_end_var, width=10).grid(row=1, column=1, padx=5, pady=2, sticky="ew") # Reduced pady
    pause_frame.grid_columnconfigure(1, weight=1)

    # Override Sleep Schedule checkbox
    override_sleep_var = tk.BooleanVar(value=True) # Set to True by default
    override_sleep_checkbox = ttk.Checkbutton(pause_frame, text="Override Sleep Schedule", variable=override_sleep_var)
    override_sleep_checkbox.grid(row=2, column=0, columnspan=2, pady=2, sticky="w") # Reduced pady


    # --- Click Settings ---
    click_settings_frame = ttk.LabelFrame(main_frame, text="Click Settings", padding="8 8 8 8") # Reduced padding
    click_settings_frame.pack(fill=tk.X, pady=5) # Reduced pady

    # Mouse Button
    mouse_button_var = tk.StringVar(value=DEFAULT_MOUSE_BUTTON)
    ttk.Label(click_settings_frame, text="Mouse Button:").grid(row=0, column=0, padx=5, pady=2, sticky="w") # Reduced pady
    
    mouse_button_radio_frame = ttk.Frame(click_settings_frame) 
    mouse_button_radio_frame.grid(row=0, column=1, columnspan=3, sticky="w", padx=0, pady=2) 

    ttk.Radiobutton(mouse_button_radio_frame, text="Left", variable=mouse_button_var, value="left").pack(side=tk.LEFT, padx=2, pady=0) # Added padx for separation
    ttk.Radiobutton(mouse_button_radio_frame, text="Right", variable=mouse_button_var, value="right").pack(side=tk.LEFT, padx=2, pady=0) # Added padx for separation
    ttk.Radiobutton(mouse_button_radio_frame, text="Middle", variable=mouse_button_var, value="middle").pack(side=tk.LEFT, padx=2, pady=0) # Added padx for separation

    # Click Type
    click_type_var = tk.StringVar(value=DEFAULT_CLICK_TYPE)
    ttk.Label(click_settings_frame, text="Click Type:").grid(row=1, column=0, padx=5, pady=2, sticky="w") # Reduced pady
    
    click_type_radio_frame = ttk.Frame(click_settings_frame) 
    click_type_radio_frame.grid(row=1, column=1, columnspan=2, sticky="w", padx=0, pady=2) 

    ttk.Radiobutton(click_type_radio_frame, text="Single", variable=click_type_var, value="single").pack(side=tk.LEFT, padx=2, pady=0) # Added padx for separation
    ttk.Radiobutton(click_type_radio_frame, text="Double", variable=click_type_var, value="double").pack(side=tk.LEFT, padx=2, pady=0) # Added padx for separation


    # --- Click Repeat ---
    click_repeat_frame = ttk.LabelFrame(main_frame, text="Click Repeat", padding="8 8 8 8") # Reduced padding
    click_repeat_frame.pack(fill=tk.X, pady=5) # Reduced pady

    click_repeat_mode_var = tk.StringVar(value=DEFAULT_CLICK_REPEAT_MODE)
    click_limit_var = tk.IntVar(value=DEFAULT_CLICK_LIMIT)

    ttk.Radiobutton(click_repeat_frame, text="Infinite Clicks", variable=click_repeat_mode_var, value="infinite", command=toggle_click_limit_entry_state).grid(row=0, column=0, padx=5, pady=2, sticky="w") # Reduced pady
    
    limited_clicks_radio = ttk.Radiobutton(click_repeat_frame, text="Limited Clicks:", variable=click_repeat_mode_var, value="limited", command=toggle_click_limit_entry_state)
    limited_clicks_radio.grid(row=1, column=0, padx=5, pady=2, sticky="w") # Reduced pady
    
    click_limit_entry = ttk.Entry(click_repeat_frame, textvariable=click_limit_var, width=8)
    click_limit_entry.grid(row=1, column=1, padx=2, pady=2, sticky="w") # Reduced pady
    click_repeat_frame.grid_columnconfigure(1, weight=1) # Allow entry to expand


    # --- Click Position (New Structure) ---
    position_frame = ttk.LabelFrame(main_frame, text="Click Position", padding="8 8 8 8")
    position_frame.pack(fill=tk.X, pady=5)

    click_location_mode_var = tk.StringVar(value=DEFAULT_CLICK_LOCATION_MODE) # Renamed variable

    # Click Mode Radio Buttons
    click_mode_radio_frame = ttk.Frame(position_frame)
    click_mode_radio_frame.pack(fill=tk.X, pady=2)
    ttk.Radiobutton(click_mode_radio_frame, text="Current Mouse Location", variable=click_location_mode_var, value="current_mouse_location", command=toggle_click_mode_controls).pack(side=tk.LEFT, padx=5, pady=0)
    ttk.Radiobutton(click_mode_radio_frame, text="Set Fixed Coordinates", variable=click_location_mode_var, value="defined_coordinates", command=toggle_click_mode_controls).pack(side=tk.LEFT, padx=5, pady=0)
    ttk.Radiobutton(click_mode_radio_frame, text="Randomized Area", variable=click_location_mode_var, value="random_area", command=toggle_click_mode_controls).pack(side=tk.LEFT, padx=5, pady=0)

    # Container for dynamic controls based on click mode
    dynamic_click_controls_frame = ttk.Frame(position_frame)
    dynamic_click_controls_frame.pack(fill=tk.X, pady=2)

    # Current Mouse Location (no specific controls needed here, just the mode selection)
    current_mouse_location_subframe = ttk.Frame(dynamic_click_controls_frame)
    ttk.Label(current_mouse_location_subframe, text="The autoclicker will click at the current mouse cursor position.", font=('Segoe UI', 7, 'italic')).pack(pady=2)

    # Fixed Point (Set Coordinates) Controls - will be packed/unpacked
    fixed_coords_subframe = ttk.Frame(dynamic_click_controls_frame)
    set_fixed_coords_button = ttk.Button(fixed_coords_subframe, text="Click to Select Coordinates (F6)", command=record_fixed_point_position) # Renamed button
    set_fixed_coords_button.pack(pady=5)
    coord_frame = ttk.Frame(fixed_coords_subframe)
    coord_frame.pack(pady=2)
    ttk.Label(coord_frame, text="X:").pack(side=tk.LEFT, padx=5)
    coord_x_label = ttk.Label(coord_frame, text="N/A", width=8, relief="sunken", borderwidth=1, background='white', foreground='#1e293b')
    coord_x_label.pack(side=tk.LEFT, padx=2)
    ttk.Label(coord_frame, text="Y:").pack(side=tk.LEFT, padx=5)
    coord_y_label = ttk.Label(coord_frame, text="N/A", width=8, relief="sunken", borderwidth=1, background='white', foreground='#1e293b')
    coord_y_label.pack(side=tk.LEFT, padx=2)
    ttk.Label(fixed_coords_subframe, text="Click the button to set a single, fixed click position.", font=('Segoe UI', 7, 'italic')).pack(pady=2)

    # Randomized Area Controls - will be packed/unpacked
    random_area_subframe = ttk.Frame(dynamic_click_controls_frame)
    draw_area_button = ttk.Button(random_area_subframe, text="Draw Area on Screen", command=start_area_selection)
    draw_area_button.pack(pady=5)
    area_coords_frame = ttk.Frame(random_area_subframe)
    area_coords_frame.pack(pady=2)
    ttk.Label(area_coords_frame, text="X1:").pack(side=tk.LEFT, padx=2)
    area_x1_label = ttk.Label(area_coords_frame, text="N/A", width=5, relief="sunken", borderwidth=1, background='white', foreground='#1e293b')
    area_x1_label.pack(side=tk.LEFT, padx=1)
    ttk.Label(area_coords_frame, text="Y1:").pack(side=tk.LEFT, padx=2)
    area_y1_label = ttk.Label(area_coords_frame, text="N/A", width=5, relief="sunken", borderwidth=1, background='white', foreground='#1e293b')
    area_y1_label.pack(side=tk.LEFT, padx=1)
    ttk.Label(area_coords_frame, text="X2:").pack(side=tk.LEFT, padx=2)
    area_x2_label = ttk.Label(area_coords_frame, text="N/A", width=5, relief="sunken", borderwidth=1, background='white', foreground='#1e293b')
    area_x2_label.pack(side=tk.LEFT, padx=1)
    ttk.Label(area_coords_frame, text="Y2:").pack(side=tk.LEFT, padx=2)
    area_y2_label = ttk.Label(area_coords_frame, text="N/A", width=5, relief="sunken", borderwidth=1, background='white', foreground='#1e293b')
    area_y2_label.pack(side=tk.LEFT, padx=1)
    ttk.Label(random_area_subframe, text="Define a rectangle for random clicks.", font=('Segoe UI', 7, 'italic')).pack(pady=2)


    # --- Control Buttons ---
    control_frame = ttk.Frame(main_frame)
    control_frame.pack(fill=tk.X, pady=5) # Reduced pady

    start_button = ttk.Button(control_frame, text="Start Autoclicker (F9)", command=start_autoclicker, style='Accent.TButton')
    start_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    stop_button = ttk.Button(control_frame, text="Stop Autoclicker (F10)", command=stop_autoclicker, state=tk.DISABLED)
    stop_button.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

    # --- Save/Load Buttons ---
    file_buttons_frame = ttk.Frame(main_frame)
    file_buttons_frame.pack(fill=tk.X, pady=5) # Reduced pady

    save_button = ttk.Button(file_buttons_frame, text="Save Settings", command=save_settings)
    save_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

    load_button = ttk.Button(file_buttons_frame, text="Load Settings", command=load_settings)
    load_button.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)


    # --- Always on Top Checkbox ---
    always_on_top_var = tk.BooleanVar(value=True) # Set to True for default checked
    always_on_top_checkbox = ttk.Checkbutton(main_frame, text="Always on Top", variable=always_on_top_var, command=toggle_always_on_top)
    always_on_top_checkbox.pack(pady=2, anchor="w") # Reduced pady

    # --- Status and Countdown ---
    status_label = ttk.Label(main_frame, text="Ready. Set your options and click Start.", font=('Segoe UI', 8, 'bold'), style='Status.TLabel') # Slightly smaller font
    status_label.pack(fill=tk.X, pady=5) # Reduced pady

    countdown_label = ttk.Label(main_frame, text="Next click in: --:--:--.--", style='Countdown.TLabel') # Updated format
    countdown_label.pack(fill=tk.X, pady=5) # Reduced pady

    # "Made by" label
    made_by_label = ttk.Label(main_frame, text="DAutoclicker - Made by Dzii420", style='MadeBy.TLabel')
    # GitHub link label
    github_link_label = ttk.Label(main_frame, text="GitHub Repository", foreground="blue", cursor="hand2", font=github_font)
    github_link_label.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/dzii420/DAutoclicker"))


    # Bind F9 key to start_autoclicker
    root.bind('<F9>', lambda event: start_autoclicker())
    # Bind F10 key to stop_autoclicker
    root.bind('<F10>', lambda event: stop_autoclicker())
    # Bind F6 key for recording fixed position (still available as an alternative)
    root.bind('<F6>', lambda event: record_click_position_f6())

    # Protocol for closing window
    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Initialize coordinates display with default values
    if CLICK_X is not None and CLICK_Y is not None:
        coord_x_label.config(text=f"{CLICK_X}")
        coord_y_label.config(text=f"{CLICK_Y}")
    
    # Initialize area coordinates display
    area_x1_label.config(text=f"{AREA_X1}")
    area_y1_label.config(text=f"{AREA_Y1}")
    area_x2_label.config(text=f"{AREA_X2}")
    area_y2_label.config(text=f"{AREA_Y2}")

    # Apply "Always on Top" setting immediately if checked by default
    toggle_always_on_top() 
    # Initialize the state of the click limit entry
    toggle_click_limit_entry_state()
    # Initialize the visibility of click mode controls
    toggle_click_mode_controls() # This will now also handle the initial visibility of made_by_label and github_link_label

    root.mainloop()

# --- Main Execution Block ---
if __name__ == "__main__":
    # Configure PyAutoGUI failsafe (move mouse to top-left corner to stop)
    pyautogui.FAILSAFE = True
    print("Starting Autoclicker GUI...")
    create_gui()
