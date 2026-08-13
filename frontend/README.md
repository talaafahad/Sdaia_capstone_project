# Bosalah Frontend

React + TypeScript + Vite + Tailwind CSS v3.

## Quick start

```bash
cd docs/frontend
npm install
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173).

## Type check (no build required)

```bash
npm run typecheck
```

## Project structure

```
src/
├── App.tsx                        # Page shell — all demo state lives here
├── main.tsx                       # Vite entry point
├── index.css                      # Tailwind directives + brand CSS vars + animations
├── types/
│   └── bosalah.ts                 # Shared TypeScript types (AgentCard, FormValues, etc.)
└── components/
    ├── HeroSection.tsx             # Brand hero, tagline, suggested chips, CTA
    ├── HowItWorks.tsx              # Hub-and-spoke diagram (SVG + lucide icons)
    ├── IntakeForm.tsx              # Controlled form (values/onChange/onSubmit props)
    ├── ProgressBar.tsx             # Purple gradient progress bar
    ├── AgentRoster.tsx             # Live agent status panel (uses ProgressBar)
    ├── ApprovalModal.tsx           # Human-in-the-loop approve/disapprove modal
    └── ConflictModal.tsx           # Side-by-side conflict resolution modal
```

## Wiring your own state

Every component is props-driven. The `useState` calls in `App.tsx` are placeholder stubs — replace them with your own store/context/Zustand/Redux slice. The component interfaces stay unchanged.

### IntakeForm

```tsx
<IntakeForm
  values={myFormState}
  onChange={(field, value) => dispatch(setField({ field, value }))}
  onSubmit={(values) => dispatch(submitCase(values))}
  onFileChange={(file) => dispatch(setDocument(file))}
/>
```

### AgentRoster

```tsx
<AgentRoster
  agents={caseState.agents}       // AgentCard[]
  overallProgress={caseState.pct} // 0–100
/>
```

### Modals

```tsx
<ApprovalModal
  isOpen={caseState.awaitingApproval}
  caseSummary={caseState.summary}
  onApprove={() => dispatch(approve())}
  onDisapprove={(reason) => dispatch(disapprove(reason))}
/>

<ConflictModal
  isOpen={caseState.hasConflict}
  conflict={caseState.activeConflict}
  onResolveConflict={(val) => dispatch(resolveConflict(val))}
  onClose={() => dispatch(dismissConflict())}
/>
```

## Demo interactions

| Action | What happens |
|---|---|
| Click a suggested-case chip | Fills the Business Goal textarea, scrolls to form |
| Click "Start Your Case" / "or fill in the form below" | Scrolls to the intake form |
| Upload a file | Triggers the Conflict modal (demo wiring only) |
| Submit the form | Triggers the Approval modal (demo wiring only) |

## Brand palette

| Token | Hex |
|---|---|
| Background (page) | `#10122B` |
| Background (cards) | `#171B3D` |
| Purple active | `#9D7CFF` |
| Green base | `#5BCD84` |
| Status amber | `#D9A441` |
| Status red | `#C0564B` |
