import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, render, screen, waitFor, fireEvent } from "@testing-library/react";
import UserPage from "./UserPage";
import { dashboardService } from "../../services/dashboard";
import { call } from "@ury/core";

vi.mock("../../context/BranchContext", () => ({
  useBranchContext: () => ({
    activeBranchId: "Kozhikode",
  }),
}));

vi.mock("../../services/dashboard", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/dashboard")>();
  return {
    ...actual,
    dashboardService: {
      getModuleRecords: vi.fn(),
    },
  };
});

vi.mock("@ury/core", async (importOriginal) => {
  const actual = await importOriginal<any>();
  return {
    ...actual,
    call: vi.fn(),
  };
});

vi.mock("@ury/ui", async (importOriginal) => {
  const actual = await importOriginal<any>();
  return {
    ...actual,
    showToast: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
  };
});

const users = [
  {
    name: "user@ury.test",
    email: "user@ury.test",
    first_name: "Test",
    last_name: "User",
    full_name: "Test User",
    enabled: 1,
    roles: [
      { role: "URY Admin" },
      { role: "URY Manager" }
    ],
  },
];

describe("UserPage", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(dashboardService.getModuleRecords).mockReset();
    vi.mocked(call).mockReset();
    vi.mocked(call).mockImplementation(async (_method, args) => ({
      message: args?.doctype === 'Role'
        ? ['URY Admin', 'URY Manager', 'URY Captain', 'URY Cashier'].map(name => ({name}))
        : args?.doctype === 'Has Role'
          ? users.flatMap(user => user.roles.map(({role}) => ({parent: user.name, role})))
          : [],
    }));
  });

  it("shows page with buttons", async () => {
    vi.mocked(dashboardService.getModuleRecords).mockResolvedValue([]);

    render(<UserPage />);
    await waitFor(() => {
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  it("displays user email and the primary URY role badge", async () => {
    vi.mocked(dashboardService.getModuleRecords).mockResolvedValue(users);

    render(<UserPage />);
    await waitFor(() => {
      expect(screen.getByText("user@ury.test")).toBeInTheDocument();
      expect(screen.getByText("URY Admin")).toBeInTheDocument();
      expect(screen.queryByText("URY Manager")).not.toBeInTheDocument();
    });
  });

  it("renders multi-select role dropdown including URY Admin when opening Add User drawer", async () => {
    vi.mocked(dashboardService.getModuleRecords).mockResolvedValue([]);

    render(<UserPage />);
    await waitFor(() => {
      const addButtons = screen.getAllByText("Add User");
      expect(addButtons.length).toBeGreaterThan(0);
    });

    const addButton = screen.getAllByText("Add User")[0];
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText("Roles / Access Level")).toBeInTheDocument();
      expect(screen.getByText("URY Cashier")).toBeInTheDocument();
    });

    // Click the MultiSelect dropdown trigger
    const selectTrigger = screen.getByText("URY Cashier").closest("div");
    if (selectTrigger) {
      fireEvent.click(selectTrigger);
    }

    await waitFor(() => {
      expect(screen.getByText("URY Admin")).toBeInTheDocument();
      expect(screen.getByText("URY Manager")).toBeInTheDocument();
      expect(screen.getByText("URY Captain")).toBeInTheDocument();
    });
  });
});
