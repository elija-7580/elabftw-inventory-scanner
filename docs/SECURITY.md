# Security

- eLabFTW API key **server-side only** (BFF env)
- Never in browser JS, localStorage, or HTML
- `ELAB_INTEGRATION_LIVE` gate for production writes
- **Server-side OIDC session required** for scanner UI and all read APIs when OIDC is configured
- Authentik OIDC: `/auth/login`, `/auth/callback` public; everything else requires `scanner_session`
- `SCANNER_ALLOW_DEV_LOGIN` — E2E tests only; must be **false** on staging/production
- CSRF: SameSite=Lax session cookie; state validated on OIDC callback
- Session cookie: `Secure`, `HttpOnly`, 1h `max_age`; cleared on login/logout
- Rate limits: TODO on BFF before production deploy

## Protected vs public (when OIDC configured)

| Route | Access |
|---|---|
| `/health` | Public (no inventory data) |
| `/auth/login` | Public |
| `/auth/callback` | Public |
| `/`, `/index.html`, `/js/*` | **Authenticated session** |
| `/api/*` | **Authenticated session** (401 JSON) |
| `/auth/session` | **Authenticated session** |
| Mutations with live gate off | 401 if unauthenticated; **403** if authenticated |

**Rejected:** embedding read/write API key in client bundles; client-only login checks; public staging without session enforcement.
