# Web platform changes

Use this checklist when a change affects HTML, CSS, client-side browser APIs or their user-visible behavior.
This includes framework components and templates that render to the web. Select only the relevant topics
from [Modern Web Guidance](https://developer.chrome.com/docs/modern-web-guidance), such as dialogs, forms,
accessibility, loading or Core Web Vitals. Consult the published guides as references.

- Read the project's supported browsers and minimum versions from its policy, Browserslist, test matrix or
  task requirements. Record what each source establishes. A build target alone does not establish the
  supported browsers. Use [Baseline](https://web.dev/baseline) and [MDN compatibility data](https://developer.mozilla.org/en-US/docs/MDN/Writing_guidelines/Page_structures/Compatibility_tables)
  to check the feature against those targets. If the targets are unknown, record the uncertainty and
  clarify it when it affects an acceptance condition.
- Inspect feature detection, progressive enhancement and fallbacks when a feature is unavailable. Check
  whether the required behavior still works and whether this change introduces a keyboard, focus,
  motion or loading regression in the affected flow. Cite the specific guide and code evidence.
- Send a runtime question to QA with the supported browser or condition, user action and expected outcome.
  For example, a changed dialog can require keyboard dismissal and focus restoration. A fallback needed
  in older browsers can require a separate scenario for that browser or an explicitly labelled simulation.

Guide recommendations inform the review. Block on a demonstrated defect against the task or supported
environment under the normal review rules. Use the published guides without installing another plugin or
running an external CLI. When guidance is unavailable, use available platform documentation and record any
material uncertainty.
