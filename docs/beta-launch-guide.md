# Closed Beta Launch Guide — HRD-603

## 1. Beta Cohort Onboarding

### Step 1: Define Tester Tiers

| Tier | Count | Audience | Distribution Channel |
|------|-------|----------|---------------------|
| **Internal** | 5–10 | Engineering team | Play Internal / TestFlight (direct) |
| **Alpha** | 15–25 | Friends/family, power users | Firebase App Distribution / TestFlight |
| **Closed Beta** | 50–100 | Target demographic | Play Internal / TestFlight |

### Step 2: Set Up Tester Groups

#### Android (Play Console)
1. Go to **Testing → Internal testing** in Play Console
2. Add tester emails under "Tester management"
3. Create separate groups if needed: `internal-testers`, `alpha-testers`

#### iOS (App Store Connect)
1. Go to **Users and Access → TestFlight → Groups**
2. Create group: "Beta Testers"
3. Add Apple IDs of testers
4. Invite via email or App Store Connect link

#### Firebase App Distribution (alternative)
```bash
firebase appdistribution:distribution groups create beta-testers \
  --app YOUR_FIREBASE_APP_ID \
  --emails tester1@example.com,tester2@example.com
```

### Step 3: Send Invitations

Use the invitation template below:

---

**Subject:** You're invited to test NutriPlan Beta! 🥗

Hi [Name],

You've been selected to be an early tester for **NutriPlan**, our AI-powered nutrition planning app.

**What you'll get:**
- Early access to meal planning features
- Personalized diet recommendations
- Direct line to the development team

**How to install:**
- **Android:** [Install via Play Store](PLAY_INTERNAL_LINK) or [Firebase App Distribution](FIREBASE_LINK)
- **iOS:** Open TestFlight and accept the invitation

**Your feedback matters!** Use the in-app Feedback screen (Profile → Beta Feedback) to report issues or suggest features.

Questions? Reply to this email or join our beta channel: [Slack/Discord link]

Thanks for helping us build a better NutriPlan!
— The NutriPlan Team

---

## 2. In-App Feedback Channel

### Location
Profile screen → "Beta Feedback" menu item (visible only during beta period)

### Categories Available
- **Bug** — Something isn't working as expected
- **Feature Request** — New functionality suggestion
- **Performance** — Speed, lag, or resource issues
- **UI/UX** — Design or usability feedback
- **Other** — General comments

### Feedback Flow
1. User selects category
2. Writes description (required) + optional steps to reproduce
3. Taps "Submit Feedback"
4. Feedback is:
   - Stored locally in SharedPreferences (for offline support)
   - Synced when network available via `POST /api/feedback`
   - Creates GitHub Issue if API key configured

### Data Schema
```json
{
  "app_version": "0.1.0-beta",
  "device_model": "Pixel 8 Pro",
  "os_version": "Android 14",
  "category": "Bug",
  "description": "App crashes when I try to save a meal plan",
  "steps_to_reproduce": "1. Open app\n2. Create new plan\n3. Add items\n4. Save",
  "timestamp": "2026-10-14T16:00:00Z",
  "user_email": "tester@example.com"
}
```

## 3. Triage Rota

### Daily Process

| Day | Owner | Responsibilities |
|-----|-------|------------------|
| Monday | [Name] | Review new feedback, categorize, assign priority |
| Tuesday | [Name] | Same as above |
| Wednesday | [Name] | Same as above |
| Thursday | [Name] | Same as above |
| Friday | [Name] | Compile weekly summary for team |

### Priority Framework

| Priority | Criteria | Response Time | Example |
|----------|----------|---------------|---------|
| **P0 — Critical** | App crash, data loss, security issue | < 4 hours | "App crashes on login" |
| **P1 — High** | Major feature broken, no workaround | < 24 hours | "Can't save meal plan" |
| **P2 — Medium** | Minor bug, workaround exists | < 72 hours | "Button misaligned on small screen" |
| **P3 — Low** | Cosmetic, enhancement request | Next sprint | "Would love dark mode for settings" |

### Weekly Cadence

- **Monday:** Triage meeting (15 min) — review P0/P1 items
- **Wednesday:** Progress check — what's been fixed since Monday
- **Friday:** Weekly summary sent to beta testers with:
  - New features shipped
  - Bugs fixed
  - Upcoming improvements
  - Thank you message

### Feedback Summary Template

```markdown
## NutriPlan Beta — Week of {DATE}

### This Week's Highlights
- ✅ Fixed: {bug fix 1}
- ✅ Fixed: {bug fix 2}
- 🚀 Shipped: {feature}

### Top Feedback Themes
1. {theme 1} — {count} reports
2. {theme 2} — {count} reports
3. {theme 3} — {count} reports

### Coming Next Week
- {planned feature/fix 1}
- {planned feature/fix 2}

Thank you to our {N} beta testers! Your feedback is shaping NutriPlan.
```

## 4. Beta Exit Criteria

Before moving from Closed Beta → GA:

- [ ] ≥ 90% of P0 issues resolved
- [ ] ≥ 75% of P1 issues resolved or have workaround
- [ ] Crash-free rate ≥ 99.5% (per HRD-605)
- [ ] ≥ 30 active testers with ≥ 2 weeks of usage data
- [ ] No critical security findings pending remediation
- [ ] Store listings approved and ready

## 5. Post-Beta Transition

### For Active Testers
Send a thank-you email with:
- Summary of what was built based on their feedback
- Invitation to join the public launch
- Optional: Early access reward (e.g., free premium month)

### For Inactive Testers
No action needed — they'll naturally discover the app at GA.

---

*HRD-603 · Phase P6 · Sprint 20 · Epic E6*
