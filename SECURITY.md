# Security policy

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead:
[Report a vulnerability](https://github.com/pandich93/creatorloop/security/advisories/new).
You will get an answer within 7 days.

## In scope

- Leaking the access token, settings or database outside the user's creatorloop home folder.
- Publishing, replying or deleting on Instagram without the user's explicit approval.
- Reading or publishing files outside the content folder.
- Anything that exposes local files through the temporary publishing tunnel beyond the files being published.

## Out of scope

- Limits and behaviour of the Instagram Graph API itself (report those to Meta).
- Problems that require an attacker to already control the user's computer or Claude Desktop config.

## Supported versions

Only the latest release receives fixes.
