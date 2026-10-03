## Course Planning Assistant
Problem Statement: Built an AI chatbot to generate personalized course plans for students. Enforced strict rules for prerequisites, graduation requirements, etc using deterministic logic and LLM based reasoning. 


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
