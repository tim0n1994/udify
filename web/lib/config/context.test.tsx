import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfigProvider, useConfig } from "./context";
import { resolveBuildConfig } from "./resolve";

function ConfigProbe() {
  const { config, diagnostics, resetPreferences, setDensity } = useConfig();
  return (
    <div>
      <output aria-label="density">{config.density}</output>
      {diagnostics.map((diagnostic) => (
        <p key={`${diagnostic.code}-${diagnostic.message}`}>{diagnostic.code}</p>
      ))}
      <button type="button" onClick={() => setDensity("compact")}>
        compact
      </button>
      <button type="button" onClick={resetPreferences}>
        reset
      </button>
    </div>
  );
}

function renderConfig() {
  return render(
    <ConfigProvider build={resolveBuildConfig()}>
      <ConfigProbe />
    </ConfigProvider>,
  );
}

describe("ConfigProvider storage failures", () => {
  it("keeps safe defaults and exposes a diagnostic when storage reads throw", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    renderConfig();

    expect(await screen.findByText("CONFIG_LOCAL_UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByLabelText("density")).toHaveTextContent("comfortable");
  });

  it("keeps an in-memory preference and exposes a diagnostic when writes throw", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("quota", "QuotaExceededError");
    });
    const user = userEvent.setup();
    renderConfig();

    await user.click(screen.getByRole("button", { name: "compact" }));

    expect(screen.getByLabelText("density")).toHaveTextContent("compact");
    expect(screen.getByText("CONFIG_LOCAL_UNAVAILABLE")).toBeInTheDocument();
  });

  it("resets in memory without throwing when storage removal is blocked", async () => {
    window.localStorage.setItem(
      "udify.display.preferences",
      JSON.stringify({ version: 1, density: "compact" }),
    );
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    const user = userEvent.setup();
    renderConfig();
    await waitFor(() =>
      expect(screen.getByLabelText("density")).toHaveTextContent("compact"),
    );

    await user.click(screen.getByRole("button", { name: "reset" }));

    expect(screen.getByLabelText("density")).toHaveTextContent("comfortable");
    expect(screen.getByText("CONFIG_LOCAL_UNAVAILABLE")).toBeInTheDocument();
  });
});
