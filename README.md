# Kai — Personal AI Assistant 🧠

> Secure FastAPI Server · Multi-Tenant Agentic RAG · iOS Shortcuts Integration · Hacker UI

Kai is a highly optimized, fully private personal AI assistant designed to act as your "second brain". It effortlessly tracks expenses, remembers random facts, and answers your questions using advanced AI (Retrieval-Augmented Generation). 

With the latest update, **Kai supports multiple users simultaneously!** Each user signs up with their email, gets their own secure "vault" of memories, and can securely sync data from their phone.

---

## 🚀 How to Use Kai (For Non-Tech Users)

If Kai is already deployed on the cloud, here is how you use it from start to finish:

### 1. Create Your Account
1. Open your Kai Live URL in your browser (e.g., `https://kai-backend-...run.app`).
2. Click **Create an Account**.
3. Enter your Name, Email, and a secure Password.
4. *Important:* Write down your **12-Word Recovery Phrase**. If you ever forget your password, this is the *only* way to reset it!

### 2. Talk to Kai
Once logged in, you will see a sleek chat interface.
- **Save a Memory:** Just tell Kai a fact! Type *"I bought a coffee for $4.50 today"* or *"My friend Sarah is allergic to peanuts"*. Kai will automatically detect that this is a fact and save it to your private vault.
- **Ask a Question:** Ask *"How much have I spent on coffee?"* or *"What is Sarah allergic to?"* Kai will scan your private vault and instantly answer!

### 3. Customize Your Profile
Click the **Profile** tab in the top right. Here you can tell Kai exactly how you want to be treated. 
- *Example:* "I am a software engineer. Only give me extremely short, factual answers without any conversational fluff."
- Kai will read these instructions before *every single response*.

---

## 📱 Automating Kai with Apple Shortcuts (iOS)

You can turn Kai into an offline, lightning-fast expense tracker using Apple Shortcuts! This setup allows you to log expenses in 2 seconds, and your phone will secretly batch-sync them to Kai at midnight to save API costs.

### Step 1: Get Your API Token
1. Log into Kai on your phone or computer.
2. Go to the **Profile** tab.
3. Tap the **Copy API Token** button. This massive string of text is your digital passport.

### Step 2: The "Log Expense" Shortcut
This shortcut asks what you bought and saves it silently to your phone.
1. Open the **Shortcuts app** on your iPhone and tap **+** to create a new shortcut. Name it "Log Expense".
2. Add an **Ask for Input** action (Prompt: "What did you buy?", Type: Text).
3. Add another **Ask for Input** action (Prompt: "How much?", Type: Number).
4. Add a **Text** action and type: `I spent [Provided Input (Number)] on [Provided Input (Text)].`
5. Add an **Append to File** action. 
   - Set it to Append **Text** to File.
   - Tap "File" and select **iCloud Drive** -> **Shortcuts**. 
   - Set File Path to `kai_expenses.txt` and ensure "Make New Line" is checked.
6. Add this shortcut to your home screen! Tap it anytime you buy something.

### Step 3: The "Sync Kai" Shortcut
This shortcut reads your expenses and sends them to your private Kai vault.
1. Create a new shortcut named "Sync Kai".
2. Add the **Get File** action (Turn OFF "Show Document Picker", Path: `kai_expenses.txt`, Turn OFF "Error If Not Found").
3. Add an **If** action: If **File** `has any value`.
4. Inside the If block, add a **Text** action: `Here are my expenses for today: [File]`
5. Inside the If block, add a **Get Contents of URL** action:
   - URL: `https://YOUR_KAI_URL.run.app/webhook`
   - Method: **POST**
   - Headers: Key = `Authorization`, Text = `Bearer <PASTE_YOUR_API_TOKEN_HERE>`
   - Request Body: **JSON**
   - Add field: `text` (Text) = `[Text]` (from step 4)
   - Add field: `source` (Text) = `ios_midnight_batch`
6. After the URL action (still inside the If block), add a **Delete File** action and set it to delete the `[File]`.

### Step 4: Midnight Automation
1. Go to the **Automation** tab in Shortcuts.
2. Create a new **Time of Day** automation for `11:59 PM` (Daily).
3. Choose **Run Immediately** (do NOT ask before running).
4. Select your **"Sync Kai"** shortcut.
*Done! Your expenses now log instantly and sync seamlessly in your sleep!*

---

## 💻 Tech Setup & Initialization (For Developers)

To host Kai yourself, follow these steps:

### 1. Environment Setup
Clone the repository and set up your `.env` file:
```bash
git clone https://gitlab.com/gourang1/askkai.git
cd askkai
cp .env.example .env
```
Edit your `.env` and configure:
- `OPENAI_API_KEY`: Your OpenAI Key (`sk-proj-...`)
- `JWT_SECRET`: A long, random, secure string used to sign user tokens. **Keep this secret!**

### 2. Local Initialization
```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000
```
Open **http://localhost:8000** in your browser.

### 3. Google Cloud Run Deployment
Kai is fully Dockerized and ready for Google Cloud Run serverless deployment. 

```bash
gcloud run deploy kai-backend \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars="OPENAI_API_KEY=your_key,JWT_SECRET=your_jwt_secret" \
  --execution-environment=gen2 \
  --add-volume=name=data-vol,type=cloud-storage,bucket=your-gcs-bucket-name \
  --add-volume-mount=volume=data-vol,mount-path=/app/data
```
> **Note:** The GCS volume mount (`/app/data`) ensures that your SQLite users database and ChromaDB vector embeddings survive across serverless container restarts. Without this, your data will wipe every time the server spins down!
