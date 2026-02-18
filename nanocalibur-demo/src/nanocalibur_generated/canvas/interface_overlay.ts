const GLOBAL_PLACEHOLDER_RE = /{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}/g;
const HAS_GLOBAL_PLACEHOLDER_RE = /{{\s*[A-Za-z_][A-Za-z0-9_]*\s*}}/;

interface TextBinding {
  node: Text;
  template: string;
}

export class InterfaceOverlay {
  private readonly root: HTMLDivElement;
  private readonly panel: HTMLDivElement;
  private readonly textBindings: TextBinding[] = [];
  private readonly buttonEvents: string[] = [];

  private readonly handleClick = (event: MouseEvent): void => {
    const buttonName = this.resolveButtonName(event.target);
    if (!buttonName) {
      return;
    }
    this.buttonEvents.push(buttonName);
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
    this.panel.addEventListener("click", this.handleClick);
  }

  setHtml(html: string): void {
    this.panel.innerHTML = html;
    this.textBindings.length = 0;
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
        (_all, name: string) => this.formatGlobalValue(globals[name]),
      );
    }
  }

  consumeButtonEvents(): string[] {
    if (this.buttonEvents.length === 0) {
      return [];
    }
    const out = [...this.buttonEvents];
    this.buttonEvents.length = 0;
    return out;
  }

  destroy(): void {
    this.panel.removeEventListener("click", this.handleClick);
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
}
