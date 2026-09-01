# Communication Evaluation Platform

A chatbot-based communication assessment platform that evaluates a candidate's communication skills through a short, structured conversation.

The assessment covers:

- Pitch / Self-Presentation
- Vocabulary
- Tonality

After completing the assessment, the platform generates individual scores, an overall communication score, strengths, areas for improvement, and the conversation transcript.

## Features

- Chatbot-based communication assessment
- Candidate name and accent selection
- Text and voice responses
- Speech-to-text using the browser Web Speech API
- Basic voice tonality analysis
- Automated rubric-based scoring
- Overall communication score
- Strengths and improvement feedback
- Complete conversation transcript
- Recruiter view for completed assessments
- SQLite data storage
- Automated backend tests

## Technologies

- Python 3.9+
- Flask
- SQLite
- HTML5
- CSS3
- JavaScript
- Web Speech API
- Python unittest

No Node.js or separate database server is required.

## Project Structure

```text
communication-evaluation-platform/
│
├── backend/
│   ├── app.py
│   ├── scoring.py
│   ├── conversation.py
│   ├── database.py
│   ├── llm_enrich.py
│   ├── requirements.txt
│   ├── run.sh
│   ├── .env.example
│   ├── tests/
│   │   ├── test_api.py
│   │   └── test_scoring.py
│   └── data/
│
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
│
├── PROJECT_REPORT.md
└── README.md
```

## How It Works

The application follows this flow:

Candidate
    ↓
Start Assessment
    ↓
Introduction
    ↓
Vendor Scenario
    ↓
Requirements / Timeline / Budget
    ↓
Follow-up
    ↓
Assessment Complete
    ↓
Scoring
    ↓
Results

The frontend provides the chatbot interface and collects candidate responses.

The Flask backend controls the assessment flow, processes responses, calculates scores, and communicates with the database.

SQLite stores assessment sessions, responses, and results.

Backend
app.py

Main Flask application and API layer.

It handles:

Starting assessments
Receiving candidate responses
Managing the conversation
Returning results
Listing completed assessments
conversation.py

Contains the assessment conversation flow and questions.

It controls the different stages of the candidate's conversation.

scoring.py

Contains the scoring logic for:

Pitch / Self-Presentation
Vocabulary
Tonality
Overall score calculation

The scoring system uses defined evaluation rules and does not require an external AI service.

database.py

Handles SQLite database operations and stores assessment information.

Frontend

The frontend uses plain HTML, CSS, and JavaScript.

app.js handles:

API requests
Conversation updates
Text responses
Voice input
Speech-to-text
Audio processing
Displaying assessment results

Voice input works best in Chrome or Edge. Text input is available as a fallback.

API Endpoints
Start Assessment
POST /assessment/start

Creates a new assessment session and returns the first conversation stage.

Submit Response
POST /assessment/<session_id>/response

Stores a candidate response and moves the assessment to the next stage.

Get Result
GET /assessment/<session_id>/result

Returns the completed assessment result.

List Assessments
GET /assessment/list

Returns completed assessments for the recruiter view.

Scoring
Pitch / Self-Presentation

Evaluates how clearly and professionally the candidate introduces themselves and communicates their purpose.

Vocabulary

Evaluates the candidate's language quality, professional wording, clarity, and use of filler words.

Tonality

Uses available voice/audio features to evaluate basic characteristics of the candidate's delivery.

If sufficient audio information is not available, the tonality score can be displayed as N/A.

Recruiter View

The recruiter view allows completed assessments to be reviewed.

It provides:

Candidate information
Individual communication scores
Overall score
Strengths
Areas for improvement
Conversation transcript

Assessment data is stored in:
backend/data/assessment.db

Requirements

Install Python 3.9 or newer.

For voice testing, use Chrome or Edge and allow microphone access.

No Node.js, external database server, or API key is required.

Running the Project

Open a terminal in the backend directory.

Install Dependencies
python -m venv venv

Windows:
venv\Scripts\activate

Then install the dependencies:
pip install -r requirements.txt

Start the Application
python app.py

Open:

http://localhost:5000
Running Tests

From the backend directory:

python -m unittest discover -s tests -v

The project includes 20 automated tests covering the API, conversation flow, scoring, aggregation, and error handling.

Current test result:

Ran 20 tests

OK
Optional Components

run.sh is a convenience script for starting the application on systems that support shell scripts. It is not required when starting the application with python app.py.

llm_enrich.py contains optional LLM-based feedback functionality. The core assessment, scoring, and results work without it.

Project Report

PROJECT_REPORT.md contains the detailed project documentation and implementation mapping.

Status

The application has been tested with both text and voice input, and the complete automated backend test suite passes successfully.
