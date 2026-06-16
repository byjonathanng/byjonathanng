# Getting started (no coding needed)

This guide sets up syncing between **Jira**, **Trello**, and your **iPhone
Reminders**. You don't need to know any code. You'll copy a few "keys" from
three websites, paste them into one file, and double-click a start button.

Set aside about **20–30 minutes** the first time. After that it just runs.

> **The honest catch about Reminders:** Apple doesn't offer a normal "connect"
> button, so we reach your Reminders through iCloud using a special password
> you create. It's a few extra clicks (Step 4), nothing hard.

---

## What you need before starting

- A Mac (the easiest way — there's a double-click start button for it).
- Your logins for Jira, Trello, and your Apple ID.
- This project folder downloaded onto your computer.

---

## Step 1 — Get your Jira key

1. Go to **https://id.atlassian.com/manage-profile/security/api-tokens**
2. Click **Create API token**. Give it a name like `tasksync`. Click **Create**.
3. Click **Copy** and paste it somewhere safe for a moment (a sticky note app).
4. Also note:
   - Your **Jira email** (the one you log in with).
   - Your **Jira web address** — looks like `https://yourcompany.atlassian.net`.
   - Your **project key** — open any ticket; the key is the letters before the
     dash, e.g. in `MKT-42` the project key is `MKT`.

---

## Step 2 — Get your Trello keys

1. Go to **https://trello.com/app-key** (log in if asked).
2. Copy the **Key** shown at the top → save it on your sticky note.
3. On that same page, find the line that says you can manually generate a
   **Token** → click it, click **Allow**, and copy the long token → save it.
4. Find the **list** you want to sync (a column on your board, like "To Do"):
   - Open your board in the browser.
   - Click the **⋯** menu on the column → you want that list's ID. The easiest
     way: add `.json` to the end of your board's web address and press Enter,
     then use your browser's Find (Cmd-F) to search for your column's name —
     the `"id"` right next to it is the **list ID**. Copy it.
   - (If that feels fiddly, tell me your board and I'll help you find it.)

---

## Step 3 — Get your Apple "app password" for Reminders

This is a one-time special password just for this tool. Your normal Apple
password will **not** work here (that's intentional, for safety).

1. Go to **https://appleid.apple.com** and sign in.
2. Go to **Sign-In and Security** → **App-Specific Passwords**.
3. Click **+** (or "Generate password"), name it `tasksync`, and click Create.
4. Copy the password it shows (looks like `abcd-efgh-ijkl-mnop`) → save it.
5. Also note the **name of the list** in your Reminders app you want to sync
   (the default one is just called `Reminders`).

> Your Reminders sync through iCloud, so make sure Reminders is turned on in
> **iPhone Settings → [your name] → iCloud**.

---

## Step 4 — Put it all into your settings file

1. In this folder, find the file **`config.starter.yaml`**.
2. Make a copy of it and rename the copy to **`config.yaml`**
   (right-click → Duplicate, then rename).
3. Open **`config.yaml`** by right-clicking → **Open With → TextEdit**.
4. Replace each `PASTE_...` with the matching value you saved, **keeping the
   quotation marks**. For example:

   ```
   email: "PASTE_YOUR_JIRA_EMAIL"
   ```
   becomes
   ```
   email: "jane@company.com"
   ```
5. Save the file (Cmd-S) and close it.

> Only syncing two of the three? Find the section you don't want and change
> its `enabled: true` to `enabled: false`.

---

## Step 5 — Start it

1. Double-click **`start.command`** in this folder.
2. A black Terminal window opens and sets things up (first time takes a
   minute). It will say **"Checking your connections…"**.
3. If everything connected, you'll see **"Everything connected. Syncing now!"**
   Leave that window open — it's doing the work. That's it. 🎉

To stop syncing, just close that window. To start again later, double-click
`start.command` again.

> The first time `start.command` runs on a Mac, macOS may say it "can't be
> opened because it is from an unidentified developer." If so: right-click the
> file → **Open** → **Open** again. You only do this once.

---

## Keeping it running all the time (optional)

The sync only happens while the Terminal window is open. If you want it to run
in the background all the time, that's possible too — tell me your setup
(always-on Mac? a spare computer?) and I'll set that up for you.

---

## If something doesn't connect

The window will tell you **which** one failed (jira, trello, or reminders).
Open `config.yaml` and re-check just that section:

- **Jira fails** → the web address, email, or API token is off. Tokens can
  only be copied once; if unsure, make a new one (Step 1) and paste it again.
- **Trello fails** → re-copy the key and token (Step 2). Make sure you clicked
  **Allow** when generating the token.
- **Reminders fails** → make sure you used the **app-specific** password
  (Step 3), not your normal Apple password, and that the `list_name` matches
  a list that really exists in your Reminders app.

Still stuck? Tell me exactly what the window said and I'll walk you through it.
