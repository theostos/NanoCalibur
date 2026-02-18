import { CanvasHostOptions } from "./types";

export class AssetStore {
  private readonly options: CanvasHostOptions;
  private readonly images = new Map<string, HTMLImageElement>();
  private loaded = false;

  constructor(options: CanvasHostOptions) {
    this.options = options;
  }

  async preload(): Promise<void> {
    if (this.loaded) {
      return;
    }

    const sources = new Map<string, string>();
    const manifest = this.options.assets || {};
    for (const [id, src] of Object.entries(manifest)) {
      sources.set(id, src);
    }

    for (const config of this.getAllSpriteConfigs()) {
      if (sources.has(config.image)) {
        continue;
      }
      const fromManifest = manifest[config.image];
      if (fromManifest) {
        sources.set(config.image, fromManifest);
      } else {
        sources.set(config.image, config.image);
      }
    }

    await Promise.all(
      Array.from(sources.entries()).map(([id, src]) => this.loadImage(id, src)),
    );
    this.loaded = true;
  }

  getImage(id: string): HTMLImageElement | undefined {
    return this.images.get(id);
  }

  private getAllSpriteConfigs() {
    const out: Array<{ image: string }> = [];
    if (this.options.spritesByType) {
      for (const value of Object.values(this.options.spritesByType)) {
        out.push(value);
      }
    }
    if (this.options.spritesByUid) {
      for (const value of Object.values(this.options.spritesByUid)) {
        out.push(value);
      }
    }
    return out;
  }

  private async loadImage(id: string, src: string): Promise<void> {
    if (this.images.has(id)) {
      return;
    }

    await new Promise<void>((resolve, reject) => {
      const image = new Image();
      image.onload = () => {
        this.images.set(id, image);
        resolve();
      };
      image.onerror = () => {
        reject(new Error(`Failed to load image '${id}' from '${src}'.`));
      };
      image.src = src;
    });
  }
}
