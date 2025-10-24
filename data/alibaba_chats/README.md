## Alibaba Chat Log Directory

This directory stores manually formatted chat logs with customers from Alibaba.

---

### 📁 File format
Each file should be named as follows:

```
[企業コード]_[YYYY-MM-DD].txt
```

Example:
```
IST_2025-10-24.txt
```

---

### 🧩 File header format
Each file must begin with:

```
[企業コード]
[担当者]
[日付]
[出典]
----------------------------------------
```

Example:
```
[企業コード] IST
[担当者] 古川 敏
[日付] 2025-10-24
[出典] Alibaba Chat
----------------------------------------
```

---

### 📝 Guidelines
- The file should contain **original chat text only** (no summary, no translation).
- Each line represents an actual message exchanged on Alibaba.
- If a summary or translation is needed, create a separate file with `_summary.md` suffix:  
  e.g. `IST_2025-10-24_summary.md`
- All files must be encoded in **UTF-8**.
- Do **not** use automated scraping or API extraction.  
  (All chat data must be copied manually to comply with Alibaba’s Terms of Service.)
- Keep the chronological order of messages for clarity.

---

### 🔍 Recommended structure
```
tousuien-hub/
 ├── data/
 │   ├── slack_threads/
 │   ├── alibaba_chats/
 │   │   ├── README.md
 │   │   ├── IST_2025-10-24.txt
 │   │   ├── MAM_2025-10-22.txt
 │   │   └── SAS_2025-10-20.txt
 │   └── Customer Management_latest.xlsx
 ├── gpt_autopush.py
 ├── Dockerfile
 ├── README.md
 └── requirements.txt
```

---

### 💡 Notes
This directory is part of the TOUSUIEN internal knowledge base.  
It is used for tracking and archiving communication history between TOUSUIEN and overseas customers via Alibaba.  
Each file corresponds to one day or one major conversation thread.

Future automation (GPT integration, Slack synchronization, etc.) will use this format as the base structure.
