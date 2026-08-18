import { fireEvent, render, screen } from "@testing-library/react";
import { SoundProvider, useSound } from "./sound-bus";

vi.mock("tone", () => {
  class Limiter {
    toDestination() {
      return this;
    }
  }
  class MembraneSynth {
    connect() {
      return this;
    }
    triggerAttackRelease = vi.fn();
    dispose() {}
  }
  return { Limiter, MembraneSynth };
});

function Probe() {
  const sound = useSound();
  return (
    <div>
      <span data-testid="state">{sound.enabled ? "on" : "off"}</span>
      <button type="button" onClick={sound.toggle}>
        切换
      </button>
      <button type="button" onClick={() => sound.play("approve")}>
        播放
      </button>
    </div>
  );
}

describe("SoundBus", () => {
  it("starts muted and toggles persisted state", () => {
    render(
      <SoundProvider>
        <Probe />
      </SoundProvider>,
    );
    expect(screen.getByTestId("state")).toHaveTextContent("off");
    fireEvent.click(screen.getByRole("button", { name: "切换" }));
    expect(screen.getByTestId("state")).toHaveTextContent("on");
    expect(window.localStorage.getItem("udify:sound-enabled")).toBe("1");
  });

  it("does not throw when playing while muted", () => {
    render(
      <SoundProvider>
        <Probe />
      </SoundProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "播放" }));
    expect(screen.getByTestId("state")).toHaveTextContent("off");
  });
});
