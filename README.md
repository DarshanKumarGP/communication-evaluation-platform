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

The platform follows a simple assessment flow:

1. Candidate starts the assessment.
2. The chatbot asks an introduction question.
3. The candidate answers a vendor-related scenario.
4. The chatbot asks follow-up questions about requirements, timeline, and budget.
5. The conversation is completed.
6. The backend calculates the communication scores.
7. The candidate receives the final results.

### Frontend

The frontend is built with HTML, CSS, and JavaScript.

It provides:

- Chatbot interface
- Text-based answers
- Voice input
- Speech-to-text using the browser Web Speech API
- Basic audio processing for tonality analysis
- Display of scores and feedback
- Recruiter view

The frontend communicates with the Flask backend through HTTP API requests.

### Backend

The backend is built with Flask and provides the main application logic.

#### `app.py`

Handles the API endpoints and controls the assessment process.

It is responsible for:

- Starting assessment sessions
- Receiving candidate responses
- Moving through conversation stages
- Completing assessments
- Returning assessment results
- Providing completed assessments for the recruiter view

#### `conversation.py`

Contains the predefined assessment conversation and controls the order of questions and follow-ups.

#### `scoring.py`

Contains the rubric-based scoring logic.

It calculates:

- Pitch / Self-Presentation score
- Vocabulary score
- Tonality score
- Overall communication score

The scoring system uses defined rules and does not require an external AI service.

#### `database.py`

Handles SQLite database operations.

It stores:

- Assessment sessions
- Candidate responses
- Conversation data
- Assessment results

### Database

The application uses SQLite, so no separate database server is required.

Assessment data is stored locally in:

`backend/data/assessment.db`

### Voice Input

The platform supports voice responses through the browser.

The browser's Web Speech API converts the candidate's speech into text.

Basic audio features are also used for tonality analysis.

Chrome and Edge are recommended for voice input. Text input is available as a fallback.

### API Endpoints

#### Start Assessment

`POST /assessment/start`

Creates a new assessment session and returns the first conversation stage.

#### Submit Response

`POST /assessment/<session_id>/response`

Stores the candidate's response and moves the assessment to the next stage.

#### Get Result

`GET /assessment/<session_id>/result`

Returns the completed assessment result.

#### List Assessments

`GET /assessment/list`

Returns completed assessments for the recruiter view.

### Scoring

#### Pitch / Self-Presentation

Evaluates how clearly and professionally the candidate introduces themselves and communicates their purpose.

#### Vocabulary

Evaluates language quality, professional wording, clarity, and use of filler words.

#### Tonality

Uses available audio features to evaluate basic characteristics of the candidate's voice delivery.

If sufficient audio information is not available, the tonality score can be shown as `N/A`.

### Recruiter View

The recruiter can view completed assessments and review:

- Candidate information
- Pitch score
- Vocabulary score
- Tonality score
- Overall score
- Strengths
- Areas for improvement
- Conversation transcript

## Requirements

- Python 3.9 or newer
- Chrome or Edge for voice input
- No Node.js required
- No separate database server required
- No API key required

## Running the Project

Open a terminal in the `backend` directory.

### Create Virtual Environment

```bash
python -m venv venv

```
## Activate Virtual Environment

Windows:

venv\Scripts\activate

Linux / macOS:

source venv/bin/activate
Install Dependencies
pip install -r requirements.txt
Start the Application
python app.py

Open the application in your browser:

http://localhost:5000

## Running Tests

From the backend directory:

python -m unittest discover -s tests -v

The project contains 20 automated tests covering the API, conversation flow, scoring, aggregation, and error handling.

## Status

The application is complete and the automated backend test suite passes successfully.
