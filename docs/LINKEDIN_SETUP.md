# LinkedIn App Setup Guide

Step-by-step instructions for creating a LinkedIn Developer App and configuring OAuth 2.0.

## 1. Create a LinkedIn App

1. Go to https://www.linkedin.com/developers/apps/new
2. Fill in:
   - **App name**: AI Content Engine
   - **LinkedIn Page**: Select your company page (required)
   - **Privacy policy URL**: Your company's privacy policy
   - **App logo**: Optional
3. Click **Create app**

## 2. Configure OAuth Settings

1. Go to the **Auth** tab of your new app
2. Note the **Client ID** and **Client Secret**
3. Under **OAuth 2.0 settings**, add redirect URLs:
   - Production: `https://content-engine-dashboard-HASH-uc.a.run.app/auth/linkedin/callback`
   - Local dev: `http://localhost:8080/auth/linkedin/callback`

## 3. Request Product Access

1. Go to the **Products** tab
2. Request access to:
   - **Share on LinkedIn** (provides `w_member_social` scope)
   - **Sign In with LinkedIn using OpenID Connect** (provides `openid profile` scopes)
3. Wait for approval (usually instant for "Share on LinkedIn", may take a few days for others)

## 4. Store Credentials in Secret Manager

```bash
# Store client credentials
echo -n "YOUR_CLIENT_ID" | gcloud secrets versions add linkedin-client-id --data-file=-
echo -n "YOUR_CLIENT_SECRET" | gcloud secrets versions add linkedin-client-secret --data-file=-
```

Or for local development, add to your `.env`:
```
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_client_secret
```

## 5. Complete OAuth Flow

1. Start the dashboard: `make local-dashboard`
2. Visit http://localhost:8080
3. Click **Connect LinkedIn** in the navigation
4. Sign in to LinkedIn and authorize the app
5. The access token is automatically stored in Secret Manager

## Token Lifecycle

- **Access tokens** expire after **60 days**
- LinkedIn does **not** provide automatic refresh tokens (only for approved partners)
- When the token expires, re-visit `/auth/linkedin` to re-authorize
- The dashboard should display a warning when the token is nearing expiration

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/oauth/v2/authorization` | GET | Start OAuth flow |
| `/oauth/v2/accessToken` | POST | Exchange code for token |
| `/v2/userinfo` | GET | Get user profile (person URN) |
| `/rest/posts` | POST | Create a LinkedIn post |

## Required Headers for Posts API

```
Authorization: Bearer {access_token}
X-Restli-Protocol-Version: 2.0.0
Linkedin-Version: 202602
Content-Type: application/json
```

## Troubleshooting

**"Unauthorized" errors**: Token likely expired. Re-run the OAuth flow.

**"Insufficient permissions"**: Make sure "Share on LinkedIn" product is approved in the Products tab.

**"Invalid redirect_uri"**: The redirect URI in the request must exactly match one configured in the Auth tab.
