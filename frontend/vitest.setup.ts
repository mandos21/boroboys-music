import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Without `globals: true`, Testing Library does not register its own teardown,
// so a rendered tree would leak into the next test in the same file.
afterEach(cleanup);
