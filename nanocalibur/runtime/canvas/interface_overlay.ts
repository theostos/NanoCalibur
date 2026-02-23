const GLOBAL_PLACEHOLDER_RE =
  /{{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*}}/g;
const HAS_GLOBAL_PLACEHOLDER_RE =
  /{{\s*[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\s*}}/;
const SINGLE_GLOBAL_PLACEHOLDER_RE =
  /^{{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*}}$/;

interface TextBinding {
  node: Text;
  template: string;
}

interface AttributeBinding {
  element: Element;
  name: string;
  template: string;
}

export interface InterfaceOverlayRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface InterfaceButtonEvent {
  name: string;
  view_id?: string;
}

export class InterfaceOverlay {
  private readonly root: HTMLDivElement;
  private readonly panel: HTMLDivElement;
  private readonly textBindings: TextBinding[] = [];
  private readonly attributeBindings: AttributeBinding[] = [];
  private readonly buttonBeginEvents: InterfaceButtonEvent[] = [];
  private readonly buttonEndEvents: InterfaceButtonEvent[] = [];
  private readonly buttonsDown = new Set<string>();
  private readonly pointerButtonById = new Map<number, string>();
  private readonly viewId: string | null;

  private readonly handlePointerDown = (event: PointerEvent): void => {
    const buttonName = this.resolveButtonName(event.target);
    if (!buttonName) {
      return;
    }
      this.pointerButtonById.set(event.pointerId, buttonName);
      if (!this.buttonsDown.has(buttonName)) {
        this.buttonsDown.add(buttonName);
        this.buttonBeginEvents.push({
          name: buttonName,
          view_id: this.viewId || undefined,
        });
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
      this.buttonEndEvents.push({
        name: buttonName,
        view_id: this.viewId || undefined,
      });
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
      this.buttonBeginEvents.push({
        name: buttonName,
        view_id: this.viewId || undefined,
      });
      this.buttonEndEvents.push({
        name: buttonName,
        view_id: this.viewId || undefined,
      });
    }
    event.preventDefault();
  };

  constructor(
    canvas: HTMLCanvasElement,
    html: string,
    viewId: string | null = null,
    rect: InterfaceOverlayRect | null = null,
  ) {
    const parent = this.resolveHostParent(canvas);
    this.root = document.createElement("div");
    this.panel = document.createElement("div");
    this.viewId = viewId;

    this.root.style.position = "absolute";
    this.root.style.zIndex = "40";
    this.root.style.pointerEvents = "none";

    this.panel.style.position = "absolute";
    this.panel.style.width = "100%";
    this.panel.style.height = "100%";
    this.panel.style.pointerEvents = "none";

    this.setRect(rect);

    this.root.appendChild(this.panel);
    parent.appendChild(this.root);

    this.setHtml(html);
    this.panel.addEventListener("pointerdown", this.handlePointerDown);
    window.addEventListener("pointerup", this.handlePointerUp);
    window.addEventListener("pointercancel", this.handlePointerCancel);
    this.panel.addEventListener("click", this.handleClick);
  }

  setRect(rect: InterfaceOverlayRect | null): void {
    if (!rect) {
      this.root.style.left = "0";
      this.root.style.top = "0";
      this.root.style.width = "100%";
      this.root.style.height = "100%";
      this.panel.style.left = "0";
      this.panel.style.top = "0";
      return;
    }
    this.root.style.left = `${rect.x}px`;
    this.root.style.top = `${rect.y}px`;
    this.root.style.width = `${rect.width}px`;
    this.root.style.height = `${rect.height}px`;
    this.panel.style.left = "0";
    this.panel.style.top = "0";
  }

  setHtml(html: string): void {
    this.panel.innerHTML = html;
    this.textBindings.length = 0;
    this.attributeBindings.length = 0;
    this.buttonBeginEvents.length = 0;
    this.buttonEndEvents.length = 0;
    this.buttonsDown.clear();
    this.pointerButtonById.clear();
    this.indexTextBindings();
    this.indexAttributeBindings();
    const clickTargets = this.panel.querySelectorAll("[data-button], button");
    for (const target of clickTargets) {
      if (target instanceof HTMLElement) {
        target.style.pointerEvents = "auto";
      }
    }
  }

  updateGlobals(globals: Record<string, any>): void {
    for (const binding of this.textBindings) {
      binding.node.textContent = this.renderTemplate(binding.template, globals);
    }
    for (const binding of this.attributeBindings) {
      const rendered = this.resolveTemplateBinding(binding.template, globals);
      const attrName = binding.name.toLowerCase();
      if (attrName === "hidden" || attrName === "disabled") {
        const enabled = this.toBoolean(rendered.raw ?? rendered.text);
        if (enabled) {
          binding.element.setAttribute(binding.name, "");
        } else {
          binding.element.removeAttribute(binding.name);
        }
        continue;
      }
      binding.element.setAttribute(binding.name, rendered.text);
    }
  }

  consumeButtonPhases(): {
    begin: InterfaceButtonEvent[];
    on: InterfaceButtonEvent[];
    end: InterfaceButtonEvent[];
  } {
    const begin = this.uniqueButtonEvents(this.buttonBeginEvents);
    const on = Array.from(this.buttonsDown.values()).map((name) => ({
      name,
      view_id: this.viewId || undefined,
    }));
    const end = this.uniqueButtonEvents(this.buttonEndEvents);
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

  private indexAttributeBindings(): void {
    const elements = this.panel.querySelectorAll("*");
    for (const element of elements) {
      const attrs = Array.from(element.attributes);
      for (const attr of attrs) {
        if (!HAS_GLOBAL_PLACEHOLDER_RE.test(attr.value)) {
          continue;
        }
        this.attributeBindings.push({
          element,
          name: attr.name,
          template: attr.value,
        });
      }
    }
  }

  private uniqueButtonEvents(events: InterfaceButtonEvent[]): InterfaceButtonEvent[] {
    const out: InterfaceButtonEvent[] = [];
    const seen = new Set<string>();
    for (const event of events) {
      const key = `${event.name}@@${event.view_id || ""}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      out.push(event);
    }
    return out;
  }

  private renderTemplate(template: string, globals: Record<string, any>): string {
    return template.replace(
      GLOBAL_PLACEHOLDER_RE,
      (_all, path: string) => this.formatGlobalValue(this.resolvePath(globals, path)),
    );
  }

  private resolveTemplateBinding(
    template: string,
    globals: Record<string, any>,
  ): { text: string; raw: unknown } {
    const singleMatch = template.match(SINGLE_GLOBAL_PLACEHOLDER_RE);
    if (!singleMatch) {
      return { text: this.renderTemplate(template, globals), raw: undefined };
    }
    const raw = this.resolvePath(globals, singleMatch[1]);
    return { text: this.formatGlobalValue(raw), raw };
  }

  private toBoolean(value: unknown): boolean {
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "number") {
      return value !== 0;
    }
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (
        normalized === "" ||
        normalized === "false" ||
        normalized === "0" ||
        normalized === "off" ||
        normalized === "no" ||
        normalized === "null" ||
        normalized === "undefined"
      ) {
        return false;
      }
      return true;
    }
    return Boolean(value);
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
