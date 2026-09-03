// vitest setup: wires jest-dom's DOM matchers (toBeInTheDocument, etc.) into
// vitest's `expect` so component tests can assert on rendered markup instead
// of just snapshotting it.
import "@testing-library/jest-dom/vitest";
