const GLOBAL_PLACEHOLDER_RE =
  /{{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*}}/g;
const HAS_GLOBAL_PLACEHOLDER_RE =
  /{{\s*[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\s*}}/;

interface TextBinding {
  node: Text;
  template: string;
}

export class InterfaceOverlay {
  private readonly root: HTMLDivElement;
  private readonly panel: HTMLDivElement;
  private readonly textBindings: TextBinding[] = [];
  private readonly buttonBeginEvents: string[] = [];
  private readonly buttonEndEvents: string[] = [];
  private readonly buttonsDown = new Set<string>();
  private readonly pointerButtonById = new Map<number, string>();

  private readonly handlePointerDown = (event: PointerEvent): void => {
    const buttonName = this.resolveButtonName(event.target);
    if (!buttonName) {
      return;
    }
    this.pointerButtonById.set(event.pointerId, buttonName);
    if (!this.buttonsDown.has(buttonName)) {
      this.buttonsDown.add(buttonName);
      this.buttonBeginEvents.push(buttonName);
    }
    event.preventDefault();
  };

  private readonly handlePointerUp = (event: PointerEvent): void => {
    const trackedButton = this.pointerButtonById.get(event.pointerId);
    if (trackedButton) {
      this.pointerButtonById.delete(event.pointerId);
    }
    const buttonName = trackedButton || this.resolveButtonName(event.target);
    if (!buttonName) {
      return;
    }
    if (this.buttonsDown.has(buttonName)) {
      this.buttonsDown.delete(buttonName);
      this.buttonEndEvents.push(buttonName);
    }
    event.preventDefault();
  };

  private readonly handlePointerCancel = (event: PointerEvent): void => {
    this.handlePointerUp(event);
  };

  private readonly handleClick = (event: MouseEvent): void => {
    const buttonName = this.resolveButtonName(event.target);
    if (!buttonName) {
      return;
    }
    if (!this.buttonsDown.has(buttonName)) {
      this.buttonBeginEvents.push(buttonName);
      this.buttonEndEvents.push(buttonName);
    }
    event.preventDefault();
  };

  constructor(canvas: HTMLCanvasElement, html: string) {
    const parent = this.resolveHostParent(canvas);
    this.root = document.createElement("div");
    this.panel = document.createElement("div");

    this.root.style.position = "absolute";
    this.root.style.left = "0";
    this.root.style.top = "0";
    this.root.style.width = "100%";
    this.root.style.height = "100%";
    this.root.style.zIndex = "40";
    this.root.style.pointerEvents = "none";

    this.panel.style.position = "absolute";
    this.panel.style.left = "0";
    this.panel.style.top = "0";
    this.panel.style.width = "100%";
    this.panel.style.height = "100%";
    this.panel.style.pointerEvents = "none";

    this.root.appendChild(this.panel);
    parent.appendChild(this.root);

    this.setHtml(html);
    this.panel.addEventListener("pointerdown", this.handlePointerDown);
    window.addEventListener("pointerup", this.handlePointerUp);
    window.addEventListener("pointercancel", this.handlePointerCancel);
    this.panel.addEventListener("click", this.handleClick);
  }

  setHtml(html: string): void {
    this.panel.innerHTML = html;
    this.textBindings.length = 0;
    this.buttonBeginEvents.length = 0;
    this.buttonEndEvents.length = 0;
    this.buttonsDown.clear();
    this.pointerButtonById.clear();
    this.indexTextBindings();
    const clickTargets = this.panel.querySelectorAll("[data-button], button");
    for (const target of clickTargets) {
      if (target instanceof HTMLElement) {
        target.style.pointerEvents = "auto";
      }
    }
  }

  updateGlobals(globals: Record<string, any>): void {
    for (const binding of this.textBindings) {
      binding.node.textContent = binding.template.replace(
        GLOBAL_PLACEHOLDER_RE,
        (_all, path: string) => this.formatGlobalValue(this.resolvePath(globals, path)),
      );
    }
  }

  consumeButtonPhases(): { begin: string[]; on: string[]; end: string[] } {
    const begin = Array.from(new Set(this.buttonBeginEvents));
    const on = Array.from(this.buttonsDown.values());
    const end = Array.from(new Set(this.buttonEndEvents));
    this.buttonBeginEvents.length = 0;
    this.buttonEndEvents.length = 0;
    return { begin, on, end };
  }

  destroy(): void {
    this.panel.removeEventListener("pointerdown", this.handlePointerDown);
    window.removeEventListener("pointerup", this.handlePointerUp);
    window.removeEventListener("pointercancel", this.handlePointerCancel);
    this.panel.removeEventListener("click", this.handleClick);
    this.buttonsDown.clear();
    this.pointerButtonById.clear();
    this.root.remove();
  }

  private resolveHostParent(canvas: HTMLCanvasElement): HTMLElement {
    const parent = canvas.parentElement || document.body;
    const computed = window.getComputedStyle(parent);
    if (computed.position === "static") {
      parent.style.position = "relative";
    }
    return parent;
  }

  private resolveButtonName(rawTarget: EventTarget | null): string | null {
    let current: Element | null =
      rawTarget instanceof Element ? rawTarget : null;
    while (current) {
      if (current instanceof HTMLElement) {
        const dataButton = current.getAttribute("data-button");
        if (dataButton && dataButton.trim()) {
          return dataButton.trim();
        }
        if (current.tagName === "BUTTON") {
          if (current.id && current.id.trim()) {
            return current.id.trim();
          }
          const nameAttr = current.getAttribute("name");
          if (nameAttr && nameAttr.trim()) {
            return nameAttr.trim();
          }
          const valueAttr = current.getAttribute("value");
          if (valueAttr && valueAttr.trim()) {
            return valueAttr.trim();
          }
        }
      }
      current = current.parentElement;
    }
    return null;
  }

  private indexTextBindings(): void {
    const walker = document.createTreeWalker(
      this.panel,
      NodeFilter.SHOW_TEXT,
    );
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (!(node instanceof Text)) {
        continue;
      }
      const template = node.textContent || "";
      if (!HAS_GLOBAL_PLACEHOLDER_RE.test(template)) {
        continue;
      }
      this.textBindings.push({ node, template });
    }
  }

  private formatGlobalValue(value: unknown): string {
    if (value === null || typeof value === "undefined") {
      return "";
    }
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean"
    ) {
      return String(value);
    }
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }

  private resolvePath(root: Record<string, any>, path: string): unknown {
    if (!root || typeof root !== "object") {
      return undefined;
    }
    const parts = path.split(".");
    let current: unknown = root;
    for (const part of parts) {
      if (!current || typeof current !== "object") {
        return undefined;
      }
      current = (current as Record<string, any>)[part];
    }
    return current;
  }
}
