# déjà view landing site

The public site for déjà view: landing page, sign-in and sign-up, a signed-in dashboard, and the privacy and terms pages. Next.js (App Router), Tailwind and Clerk.

## Running it

```bash
cp .env.example .env.local   # then fill in the two Clerk keys
npm install
npm run dev
```

Open http://localhost:3000. The app does not start without the Clerk keys.

| Variable | What it is |
|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key (starts with `pk_`) |
| `CLERK_SECRET_KEY` | Clerk secret key (starts with `sk_`). Never commit it. |
| `NEXT_PUBLIC_SITE_URL` | Public address of this site, used in canonical and Open Graph URLs |
| `NEXT_PUBLIC_ANALYZER_URL` | Where the analysis app in `../Frontend` is served; the dashboard links to it |
| `NEXT_PUBLIC_API_URL` | Where the analysis API in `../Backend` is served; the dashboard shows whether it is up |

## Where things are

- `lib/site.ts`: brand name, description, contact and legal details. Two legal details are still missing there (postal address, governing country or state) and show as "to be added before launch" on the legal pages.
- `app/page.tsx`: the landing page. Each number in the copy is traced to its source in a comment at the top.
- `app/dashboard/`: signed-in area. Access is checked in the layout and again in the page.
- `proxy.ts`: Clerk request handling (called `middleware.ts` before Next.js 16).
- `app/privacy`, `app/terms`: legal text. It has not been reviewed by a lawyer and must be before launch.
