A thin determinate progress bar. `info` fill while running, `ok` when complete; `striped` signals a rate-limited / waiting job.

```jsx
<ProgressBar value={45} />
<ProgressBar value={100} tone="ok" />
<ProgressBar value={0} striped />
```
