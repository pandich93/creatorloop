# Meta setup: app, token and account ID

creatorloop uses the official **Instagram API with Facebook Login**
([Meta docs](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login)).
You create your own Meta app once; it stays in Development mode and needs no App Review for your own account.

> Meta renames menu items almost every year. If a label below doesn't match, follow the meaning of the step and
> the linked Meta docs.

## 0. Before you start

1. An Instagram **Business** or **Creator** account. Switch in the app: *Settings → Account type and tools*
   ([help](https://help.instagram.com/502981923235522)).
2. A **Facebook Page** linked to that Instagram account. Without it, competitor analysis (Business Discovery) and
   hashtag search do not work.
3. A developer account at [developers.facebook.com](https://developers.facebook.com).
4. creatorloop installed: `uvx --from creatorloop creatorloop-setup` (see the [README](../README.md#quick-start)).

## 1. Create the app

1. [developers.facebook.com](https://developers.facebook.com) → *My Apps* → *Create App* → type **Business**.
2. In the app: *Add product* → **Instagram** → **API setup with Facebook login**.
   Not "with Instagram login": that variant has no Business Discovery and no hashtag search.
3. *App settings → Basic*: copy **App ID** and **App Secret** into your settings file as `META_APP_ID` and
   `META_APP_SECRET`. `creatorloop-setup` printed where the file is.

## 2. Get a token (60 days)

1. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/), pick your app → *User Token*, and add
   these permissions:

   | Permission | Used for |
   |---|---|
   | `instagram_basic` | profile and media |
   | `instagram_manage_insights` | private insights, demographics |
   | `pages_show_list`, `pages_read_engagement` | finding the Instagram account through your Page |
   | `business_management` | Business Discovery |
   | `instagram_content_publish` | publishing posts and Reels |
   | `instagram_manage_comments` | reading and answering comments |

2. *Generate Access Token* and allow access to your Page and Instagram account. This token lives 1–2 hours.
3. Exchange it for a 60-day token and save your account ID
   ([how the exchange works](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived)):

   ```bash
   uvx --from creatorloop creatorloop-auth exchange --short-token <TOKEN_FROM_EXPLORER> --write
   uvx --from creatorloop creatorloop-auth whoami --write
   uvx --from creatorloop creatorloop-auth check
   ```

   `check` should print `OK: @your_account followers=...`. Restart Claude Desktop.

## 3. A token that never expires (recommended)

A user token lasts 60 days; creatorloop warns 14 days ahead (`token_warning` in answers, days left in
`get_api_status`). To stop renewing it, use a **System User** token
([Meta docs](https://developers.facebook.com/docs/marketing-api/system-users),
[Business help](https://www.facebook.com/business/help/503306463479099)):

1. Open [business.facebook.com/settings](https://business.facebook.com/settings). Your app, Facebook Page and
   Instagram account must be in **one business portfolio**. Link the app in *App settings → Basic → Business portfolio*.
2. *Users → System users → Add*. Any name (e.g. `creatorloop`), role *Admin*.
3. *Assign assets*: *Apps* → your app (full control); *Pages* → your Page; *Instagram accounts* → your account.
4. *Generate token* → your app → expiry **Never** → the same permissions as in step 2.
5. Put it into the settings file as `IG_ACCESS_TOKEN` and run `creatorloop-auth check`. Expected: `Token never expires`.
6. Restart Claude Desktop.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Missing required settings: IG_ACCESS_TOKEN, IG_USER_ID` | Fill both in the settings file printed by `creatorloop-setup`, restart Claude Desktop |
| Error code 190 (token) | The token expired or was revoked: repeat step 2 or use a System User token (step 3) |
| Hashtag search fails with a permission error | Meta may require *Instagram Public Content Access* (App Review) for your account |
| `get_competitor` fails for an account | Only public Business/Creator accounts work; personal, private and 18+ accounts are not available |
| Demographics are empty | Meta returns them only for accounts with 100+ followers |
| Rate-limit errors (codes 4, 17, 32, 613) | Wait; `get_api_status` shows the current usage. creatorloop does not retry these |
