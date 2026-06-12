# Kai — Personal AI Assistant 🧠

> **Secure FastAPI Server · Multi-Tenant Agentic RAG · iOS Shortcuts Integration**

Kai is a highly optimized, fully private personal AI assistant designed to act as your "second brain". It effortlessly tracks expenses, remembers random facts, and answers complex questions using an advanced **Agentic Retrieval-Augmented Generation (RAG)** architecture.

With its latest update, **Kai supports multiple concurrent users!** Each user signs up with their email, gets their own cryptographically secure "vault" of memories, and can silently sync data offline from their iPhone.

---

## 🛠️ System Architecture

Kai is engineered for scale, privacy, and low-latency responses, leveraging a modern AI tech stack:

- **Agentic LLM Intent Router:** Replaced brittle heuristic/math-based routing with a dynamic LLM intent classifier (`gpt-4o-mini`). Kai intelligently understands the semantic difference between *"I make 100k"* (SAVE) and *"How much do I make?"* (QUERY), automatically executing the correct downstream pipeline.
- **Persistent RAG Pipeline:** Integrates **ChromaDB** for highly accurate semantic vector search, allowing Kai to retrieve the exact memories needed to answer questions in milliseconds.
- **Relational Graph Engine:** Built a custom **SQLite-backed graph extraction engine** that dynamically parses unstructured text into `(Entity-Relation-Entity)` tuples, allowing Kai to query 1-hop subgraphs to understand complex relational contexts.
- **Multi-Tenant FastAPI Backend:** A highly concurrent **FastAPI** server using secure **JWT-based authentication** and **Bcrypt** hashing. Users are strictly isolated in their own data directories.
- **Deep Sleep Memory Consolidation:** An automated memory compaction algorithm that chunks and merges disjointed facts into dense, structured summaries—drastically reducing context-window token costs and improving AI accuracy over time.
- **Serverless GCP Cloud Run Deployment:** Fully Dockerized and deployed to **Google Cloud Run**, elegantly handling **GCS Fuse** filesystem limitations to achieve a robust, stateless serverless architecture with persistent cloud storage mounts.

---

## 🚀 How to Use Kai

If Kai is already deployed on the cloud, here is how you use it:

### 1. Create Your Account

1. Open your Kai Live URL in your browser.
2. Click **Create an Account**.
3. Enter your Name, Email, and a secure Password.
4. *Important:* Write down your **12-Word Recovery Phrase**. If you ever forget your password, this is the *only* way to reset it!

### 2. Talk to Kai

Once logged in, you will see a sleek chat interface.

- **Save a Memory:** Just tell Kai a fact! Type *"I bought a coffee for $4.50 today"* or *"My friend Sarah is allergic to peanuts"*. Kai's **LLM Router** will instantly detect that this is a fact and save it to your private vault.
- **Ask a Question:** Ask *"How much have I spent on coffee?"* or *"What is Sarah allergic to?"* Kai will scan your private vector database and instantly answer!
- **Do Both at Once:** Type *"I spent $50 on groceries, how much money do I have left?"* Kai's router will smartly save your expense *and* answer your question in one go!

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
2. Add the **Get File** action (Turn OFF "Show Document Picker", Path: `kai_expenses.txt`, Turn OFF "Error If Not Found"). *Ensure this is explicitly pulling from the `Shortcuts` folder!*
3. Add an **If** action: If **File** `has any value`.
4. Inside the If block, add a **Text** action: `Here are my expenses for today: [File]`
5. Inside the If block, add a **Get Contents of URL** action:
   - URL: `https://YOUR_KAI_URL.run.app/webhook` *(Important: it must end with /webhook)*
   - Method: **POST**
   - Headers: Key = `Authorization`, Text = `Bearer <PASTE_YOUR_API_TOKEN_HERE>`
   - Request Body: **JSON**
   - Add field: `text` (Text) = `[Text]` (from step 4)
   - Add field: `source` (Text) = `ios_midnight_batch`
6. To avoid iOS privacy popups asking for permission to delete files, we will use an overwrite hack!
7. Still inside the If block, add a blank **Text** action (do not type anything inside it).
8. Add a **Save File** action. Set it to save the blank `[Text]` to `kai_expenses.txt`. Tap the arrow on the block and turn **ON** `Overwrite If File Exists`.

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

Open **<http://localhost:8000>** in your browser.

### 3. Google Cloud Run Deployment

Kai is fully Dockerized and ready for Google Cloud Run serverless deployment.

```bash
gcloud run deploy kai-backend \
  --source . \
  --region asia-south1 \
  --project united-project-j7 \
  --allow-unauthenticated \
  --set-env-vars="OPENAI_API_KEY=your_key,JWT_SECRET=your_jwt_secret" \
  --execution-environment=gen2 \
  --add-volume=name=data-vol,type=cloud-storage,bucket=kai-memory-data \
  --add-volume-mount=volume=data-vol,mount-path=/app/data
```

> **Note:** The GCS volume mount (`/app/data`) ensures that your SQLite users database and ChromaDB vector embeddings survive across serverless container restarts. Without this, your data will wipe every time the server spins down!
