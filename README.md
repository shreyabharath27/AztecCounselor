## Course Planning Assistant
Problem Statement: Built an AI chatbot to generate personalized course plans for students. Enforced strict rules for prerequisites, graduation requirements, etc using deterministic logic and LLM based reasoning. 

## Tech Stack and Architecture

- **Frontend:** Next.js, React, and TypeScript
  - Provides the user interface
  - Uploads transcripts and displays generated degree plans

- **Backend:** FastAPI and Python
  - Handles API requests
  - Extracts transcript data
  - Coordinates database, storage, and AI operations

- **Database:** PostgreSQL
  - Stores students, degree requirements, completed courses, and generated plans

- **File Storage:** Amazon S3
  - Stores uploaded transcript files

- **AI Service:** Amazon Bedrock
  - Converts transcript text into structured course data
  - Generates personalized degree plans


## System Architecture

```mermaid
flowchart TD
    User["Student uploads transcript"] --> Frontend["Frontend: Next.js, React, TypeScript"]
    Frontend -->|"Send transcript"| API["FastAPI backend"]

    API -->|"Store transcript PDF"| S3["Amazon S3"]
    S3 --> Extractor["PDF transcript extraction"]
    Extractor -->|"Transcript text and analysis prompt"| Analysis["Amazon Bedrock: Transcript Analysis"]

    Analysis -->|"Completed courses JSON"| API
    API -->|"Save student and course completion data"| Database[("PostgreSQL")]

    Database -->|"Student progress and degree requirements"| API
    API -->|"Student data and planning prompt"| Planner["Amazon Bedrock: Course Planning"]

    Planner -->|"Generated course plan JSON"| API
    API -->|"Save generated plan"| Database
    API -->|"Return course plan"| Frontend
    Frontend --> Results["Display personalized degree plan"]
```
