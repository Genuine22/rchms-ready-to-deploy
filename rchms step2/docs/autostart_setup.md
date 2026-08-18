# RCHMS - Auto-Start Setup Guide

This guide sets up the system so you don't have to manually open
Command Prompt every day. After this, both the Admin Server and each
Client Agent will start automatically when their PC turns on.

We use Windows **Task Scheduler** because it's more reliable than the
Startup folder for programs that need to keep running continuously
(like our server and agent).

---

## Part 1: Auto-start the SERVER (on the Admin PC)

### Step 1: Confirm the batch file works manually first

1. Go to your server folder (e.g. `C:\Users\Jnr\Downloads\rchms step2\server`)
2. Find the new file **`start_server.bat`**
3. Double-click it
4. A black window should open and show the server starting (same as
   running `python run.py` normally)
5. Confirm it works by visiting `http://localhost:5000` in a browser
6. Close that window when done testing (Ctrl+C inside it, then close)

### Step 2: Open Task Scheduler

1. Press **Windows key**, type "Task Scheduler", open it

### Step 3: Create a new task

1. In the right-hand panel, click **"Create Task..."** (not "Create Basic Task" - we need the full version for one extra setting)
2. **General tab:**
   - Name: `RCHMS Server`
   - Check **"Run with highest privileges"**
   - Under "Configure for," leave as is (Windows 10/11)
3. **Triggers tab:**
   - Click **New...**
   - Begin the task: **"At log on"**
   - Specific user: select your own Windows user account
   - Click OK
4. **Actions tab:**
   - Click **New...**
   - Action: "Start a program"
   - Program/script: click **Browse**, navigate to and select `start_server.bat`
     (e.g. `C:\Users\Jnr\Downloads\rchms step2\server\start_server.bat`)
   - Start in (optional): paste the same folder path, e.g.
     `C:\Users\Jnr\Downloads\rchms step2\server`
   - Click OK
5. **Conditions tab:**
   - Uncheck "Start the task only if the computer is on AC power" (if present) - useful if this is ever on a laptop
6. **Settings tab:**
   - Check "Allow task to be run on demand"
   - Uncheck "Stop the task if it runs longer than" (or set it very high) - the server needs to run continuously, not be killed after a few hours
7. Click **OK** to save the task (enter your Windows password if prompted)

### Step 4: Test it

1. Restart the Admin PC (or log out and log back in)
2. Wait about 30 seconds after logging back in
3. Open a browser, go to `http://localhost:5000`
4. You should see the login page without having opened Command Prompt yourself

If it doesn't work, open Task Scheduler again, find "RCHMS Server" in
the task list, right-click it, and choose **"Run"** to test it
immediately and see if any error appears.

---

## Part 2: Auto-start the CLIENT AGENT (on each client PC)

Repeat the same steps on **each client PC**, with these differences:

- Use **`start_agent.bat`** instead of `start_server.bat` (found in the
  `client_agent` folder, e.g. `C:\client_agent\start_agent.bat`)
- Name the task `RCHMS Client Agent` instead
- "Start in" should point to the `client_agent` folder, e.g. `C:\client_agent`

Test it the same way: restart the client PC, wait a moment, and the
small countdown window should appear automatically in the corner,
without you needing to open Command Prompt.

---

## Checking logs if something goes wrong

Both the server and the agent now keep a log file you can check:

- **Server**: `server\logs\error.log` (only logs actual errors, not
  normal activity) and `server\server_log.txt` (everything printed
  when started via `start_server.bat`)
- **Client Agent**: `client_agent\agent_log.txt` (connection issues,
  lock events, and any crashes)

If something isn't working as expected, open these files in Notepad
and look at the most recent lines (bottom of the file) - that'll show
you or Claude what actually happened.

---

## Important notes

- **Debug mode is now OFF** by default for the server. This means
  Flask will no longer auto-restart itself when files change, and
  error pages shown to users will be friendly/generic instead of
  showing full technical details. If you ever need full error details
  back temporarily (e.g. while working with Claude on a bug), add this
  line to your `.env` file: `DEBUG_MODE=true`, then restart the server.
- Since debug mode is off, **you must manually restart the server**
  (close the window, run `start_server.bat` again, or use Task
  Scheduler's "Run" option) any time new files are copied in.
