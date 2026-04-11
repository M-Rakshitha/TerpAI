# TerpAI Frontend

## Overview

TerpAI is a multi-agent AI platform designed for University of Maryland students. It integrates various university services into a single conversational assistant, allowing users to interact through natural language queries.

## Project Structure

The frontend of the TerpAI project is organized as follows:

```
frontend/
├── app/                     # Application pages and API routes
│   ├── layout.tsx          # Layout structure for the application
│   ├── page.tsx            # Main entry point for the application
│   ├── login/               # Login page for user authentication
│   │   └── page.tsx
│   └── api/                 # API routes for authentication
│       └── auth/
│           └── [...auth0]/
│               └── route.ts
├── components/              # Reusable components for the application
│   ├── chat/                # Chat-related components
│   │   ├── ChatInput.tsx
│   │   └── ChatHistory.tsx
│   ├── cards/               # Components for displaying various data cards
│   │   ├── ScheduleCard.tsx
│   │   ├── DiningCard.tsx
│   │   ├── EventsCard.tsx
│   │   ├── FinanceCard.tsx
│   │   ├── NavigatorCard.tsx
│   │   ├── StudyResourcesCard.tsx
│   │   └── JobsResearchCard.tsx
│   ├── dashboard/           # Dashboard component
│   │   └── Dashboard.tsx
│   └── ui/                  # UI components from ShadCN
├── lib/                     # Library functions and types
│   ├── api.ts               # API call functions
│   ├── types.ts             # TypeScript interfaces
│   └── mockData.ts          # Mock data for testing
├── hooks/                   # Custom hooks
│   └── useQuery.ts          # Hook for managing API query state
├── public/                  # Static assets
├── .env.local               # Environment variables
├── package.json             # npm configuration
├── tsconfig.json            # TypeScript configuration
├── next.config.js           # Next.js configuration
└── README.md                # Project documentation
```

## Setup Instructions

1. Clone the repository:
   ```
   git clone <repository-url>
   cd frontend
   ```

2. Install dependencies:
   ```
   npm install
   ```

3. Create a `.env.local` file in the root directory and add your environment variables:
   ```
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_USE_MOCK=true
   AUTH0_SECRET=<your-auth0-secret>
   AUTH0_BASE_URL=http://localhost:3000
   AUTH0_ISSUER_BASE_URL=https://your-tenant.us.auth0.com
   AUTH0_CLIENT_ID=<your-client-id>
   AUTH0_CLIENT_SECRET=<your-client-secret>
   AUTH0_AUDIENCE=https://terpai.api
   NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=<your-google-maps-api-key>
   ```

4. Run the development server:
   ```
   npm run dev
   ```

5. Open your browser and navigate to `http://localhost:3000` to view the application.

## Usage Guidelines

- Use the chat interface to interact with the TerpAI assistant.
- The dashboard will display relevant information based on your queries.
- Ensure to authenticate using the login page before accessing the main features.

## Contributing

Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.