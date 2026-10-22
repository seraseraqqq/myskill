# Browser-Game Quality Checklist

Use this as a practical review, not a fixed aesthetic formula. The visual treatment should fit the specific game, player, device, and monetization model.

## Player Experience

- [ ] A player can identify the game and begin play without confusing navigation or unnecessary steps.
- [ ] Controls, score, pause/restart, instructions, and game-over states are legible and consistent with the game.
- [ ] Layout works at common desktop and mobile widths; the game remains usable without clipping or accidental page scrolling.
- [ ] Touch and keyboard controls are tested where applicable; focus indicators and reduced-motion preferences are respected where relevant.
- [ ] Ads do not resemble controls, cover gameplay, or sit where accidental clicks are likely.

## Content and Trust

- [ ] Page copy answers real player questions and makes no unsupported claims.
- [ ] FAQs are included only when answers are accurate, useful, and specific to this implementation.
- [ ] Game name, screenshots, artwork, audio, and code have documented rights/attribution.
- [ ] Privacy, analytics, embeds, and ad disclosures are appropriate for the selected audience and markets.

## Visual Review

- [ ] Gameplay is prominent, but no universal viewport-height ratio is required.
- [ ] Visual hierarchy makes the game, primary controls, and important states easy to find.
- [ ] Components are not nested decoratively; borders, shadows, motion, and color serve usability or game identity.
- [ ] Text fits at narrow widths, has sufficient contrast, and does not overlap controls or gameplay.
- [ ] Reference sites are used for comparative inspiration, not copied or treated as mandatory templates.

## Release Verification

- [ ] Game loads and completes a real play loop on desktop and mobile.
- [ ] Refresh behavior, persistence, offline behavior, and data-loss limitations are understood.
- [ ] Production build has no material console errors, missing resources, or unexpected third-party requests.
- [ ] Performance is tested on representative devices/network conditions and actual results are recorded; no score is assumed.
- [ ] Canonical, indexability, title, description, sitemap, and robots settings are checked at the deployed URL.
- [ ] Ads remain disabled unless eligibility and provider policy checks have passed.
