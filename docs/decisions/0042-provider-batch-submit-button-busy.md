# 0042 Provider Batch Submit Button Busy State

## Context

Provider Batch submission updates the job list after `submit_images()` returns, but users do not
always notice that the click was accepted while the provider upload/create call is running.

## Decision

The Provider Batch `送信` button represents only the synchronous submit call state. While
`submit_images()` is running, the button is disabled, changes to `送信中...`, and uses a temporary
busy style. After the call returns or raises, the button returns to the normal `送信` state.

## Rationale

This keeps the first UX improvement small and avoids adding popup, toast, banner, or row highlight
behavior before it is proven necessary. The job table remains responsible for asynchronous provider
job progress after the job has been registered.

## Consequences

Tests must cover both successful submission and failure paths so the button cannot remain disabled
after a provider or validation error. Future notification work should be added as a separate UX
iteration instead of overloading the button with asynchronous job completion state.
