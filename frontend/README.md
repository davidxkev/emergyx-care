# Emergyx Care Frontend

Separate Next.js frontend using the generated MVP Blocks admin dashboard shell.

## Setup

```bash
cp .env.local.example .env.local
npm install
```

Default API target:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Run

```bash
npm run dev
```

Open:

```text
http://localhost:3000/dashboard?mode=demo
http://localhost:3000/reports?mode=demo
http://localhost:3000/chat?mode=demo
```

For the Docker judge demo, run from the repo root:

```bash
./scripts/start_demo.sh
```
