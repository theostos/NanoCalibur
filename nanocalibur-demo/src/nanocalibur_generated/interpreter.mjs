export class NanoCaliburInterpreter {
  constructor(spec, actionFns, predicateFns = {}) {
    this.spec = spec || {};
    this.actionFns = actionFns || {};
    this.predicateFns = predicateFns || {};

    this.actors = this._initActors(this.spec.actors || []);
    this.globals = this._initGlobals(this.spec.globals || []);
    this.rules = this.spec.rules || [];
    this.map = this.spec.map || null;
    this.cameraConfig = this.spec.camera || null;
    this.predicateMeta = this._buildPredicateMeta(this.spec.predicates || []);
    this._solidTiles = this._buildSolidTileSet(this.map);
  }

  tick(frame = {}) {
    const context = this._buildContext();
    for (const rule of this.rules) {
      if (this._conditionMatches(rule.condition, frame)) {
        const fn = this.actionFns[rule.action];
        if (typeof fn !== "function") {
          throw new Error(`Missing action function '${rule.action}'.`);
        }
        fn(context);
      }
    }
  }

  getState() {
    return {
      globals: this.globals,
      actors: this.actors,
      camera: this.getCameraState(),
      map: this.map,
    };
  }

  getCameraState() {
    if (!this.cameraConfig) {
      return null;
    }
    if (this.cameraConfig.mode === "fixed") {
      return {
        mode: "fixed",
        x: this.cameraConfig.x,
        y: this.cameraConfig.y,
      };
    }
    if (this.cameraConfig.mode === "follow") {
      const actor = this._getActorByUid(this.cameraConfig.target_uid);
      return {
        mode: "follow",
        target_uid: this.cameraConfig.target_uid,
        x: actor && typeof actor.x === "number" ? actor.x : 0,
        y: actor && typeof actor.y === "number" ? actor.y : 0,
      };
    }
    return null;
  }

  isSolidAtWorld(worldX, worldY) {
    if (!this.map) {
      return false;
    }
    const tileSize = this.map.tile_size;
    const tileX = Math.floor(worldX / tileSize);
    const tileY = Math.floor(worldY / tileSize);
    return this._solidTiles.has(`${tileX},${tileY}`);
  }

  _buildContext() {
    return {
      globals: this.globals,
      actors: this.actors,
      getActorByUid: (uid) => this._getActorByUid(uid),
    };
  }

  _initGlobals(globalsSpec) {
    const globals = {};
    for (const globalVar of globalsSpec) {
      if (globalVar.kind === "actor_ref") {
        const payload = globalVar.value || {};
        globals[globalVar.name] = this._getActorByUid(payload.uid);
      } else {
        globals[globalVar.name] = globalVar.value;
      }
    }
    return globals;
  }

  _initActors(actorSpecs) {
    return actorSpecs.map((actor) => ({
      uid: actor.uid,
      type: actor.type,
      ...(actor.fields || {}),
    }));
  }

  _buildSolidTileSet(mapSpec) {
    const tiles = new Set();
    if (!mapSpec || !Array.isArray(mapSpec.solid_tiles)) {
      return tiles;
    }
    for (const tile of mapSpec.solid_tiles) {
      if (Array.isArray(tile) && tile.length === 2) {
        tiles.add(`${tile[0]},${tile[1]}`);
      }
    }
    return tiles;
  }

  _buildPredicateMeta(predicateDefs) {
    const out = {};
    for (const item of predicateDefs) {
      if (typeof item === "string") {
        out[item] = { actor_type: null };
      } else if (item && typeof item.name === "string") {
        out[item.name] = { actor_type: item.actor_type || null };
      }
    }
    return out;
  }

  _conditionMatches(condition, frame) {
    if (!condition || typeof condition !== "object") {
      return false;
    }

    if (condition.kind === "keyboard" || condition.kind === "keyboard_pressed") {
      const phase = condition.phase || "on";
      return this._matchKeyboardPhase(frame, phase, condition.key);
    }

    if (condition.kind === "mouse" || condition.kind === "mouse_clicked") {
      const phase = condition.phase || "on";
      return this._matchMousePhase(frame, phase, condition.button || "left");
    }

    if (condition.kind === "collision") {
      const collisions = Array.isArray(frame.collisions) ? frame.collisions : [];
      for (const collision of collisions) {
        const [a, b] = this._resolveCollisionPair(collision);
        if (!a || !b) {
          continue;
        }
        const direct =
          this._matchesSelector(condition.left, a) &&
          this._matchesSelector(condition.right, b);
        const swapped =
          this._matchesSelector(condition.left, b) &&
          this._matchesSelector(condition.right, a);
        if (direct || swapped) {
          return true;
        }
      }
      return false;
    }

    if (condition.kind === "logical") {
      const fn = this.predicateFns[condition.predicate];
      if (typeof fn !== "function") {
        throw new Error(`Missing predicate function '${condition.predicate}'.`);
      }
      const predicateType =
        this.predicateMeta[condition.predicate] &&
        this.predicateMeta[condition.predicate].actor_type;
      const selected = this._selectActors(condition.target).filter((actor) => {
        if (!predicateType) {
          return true;
        }
        return actor.type === predicateType;
      });
      return selected.some((actor) => Boolean(fn(actor)));
    }

    return false;
  }

  _resolveCollisionPair(collision) {
    if (!collision || typeof collision !== "object") {
      return [null, null];
    }
    if (collision.a && collision.b) {
      return [collision.a, collision.b];
    }
    if (collision.aUid && collision.bUid) {
      return [this._getActorByUid(collision.aUid), this._getActorByUid(collision.bUid)];
    }
    if (Array.isArray(collision.uids) && collision.uids.length === 2) {
      return [this._getActorByUid(collision.uids[0]), this._getActorByUid(collision.uids[1])];
    }
    return [null, null];
  }

  _matchKeyboardPhase(frame, phase, key) {
    const keyboard = frame.keyboard || {};
    const begin = this._normalizeStringArray(
      keyboard.begin || frame.keysJustPressed || frame.keysBegin || []
    );
    const on = this._normalizeStringArray(
      keyboard.on || frame.keysPressed || frame.keysDown || []
    );
    const end = this._normalizeStringArray(
      keyboard.end || frame.keysJustReleased || frame.keysEnd || []
    );
    return this._phaseArrayContains(phase, begin, on, end, key);
  }

  _matchMousePhase(frame, phase, button) {
    const mouse = frame.mouse || {};
    const begin = this._normalizeStringArray(
      mouse.begin || frame.mouseButtonsJustPressed || []
    );
    const on = this._normalizeStringArray(
      mouse.on || frame.mouseButtons || []
    );
    const end = this._normalizeStringArray(
      mouse.end || frame.mouseButtonsJustReleased || []
    );

    if (phase === "on" && begin.length === 0 && on.length === 0 && end.length === 0) {
      const clicked = frame.mouseClicked;
      if (typeof clicked === "boolean") {
        return clicked;
      }
      if (clicked && typeof clicked === "object" && typeof clicked.button === "string") {
        return clicked.button === button;
      }
    }

    return this._phaseArrayContains(phase, begin, on, end, button);
  }

  _phaseArrayContains(phase, begin, on, end, value) {
    if (phase === "begin") {
      return begin.includes(value);
    }
    if (phase === "end") {
      return end.includes(value);
    }
    return on.includes(value);
  }

  _normalizeStringArray(value) {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .filter((item) => typeof item === "string")
      .map((item) => item);
  }

  _selectActors(selector) {
    if (!selector || typeof selector !== "object") {
      return [];
    }
    if (selector.kind === "with_uid") {
      const actor = this._getActorByUid(selector.uid);
      if (!actor) {
        return [];
      }
      if (selector.actor_type && actor.type !== selector.actor_type) {
        return [];
      }
      return [actor];
    }

    if (selector.kind === "any") {
      if (!selector.actor_type) {
        return [...this.actors];
      }
      return this.actors.filter((actor) => actor.type === selector.actor_type);
    }

    return [];
  }

  _matchesSelector(selector, actor) {
    if (!actor || !selector) {
      return false;
    }
    if (selector.kind === "with_uid") {
      if (selector.uid !== actor.uid) {
        return false;
      }
      if (selector.actor_type && selector.actor_type !== actor.type) {
        return false;
      }
      return true;
    }
    if (selector.kind === "any") {
      if (!selector.actor_type) {
        return true;
      }
      return selector.actor_type === actor.type;
    }
    return false;
  }

  _getActorByUid(uid) {
    return this.actors.find((actor) => actor.uid === uid);
  }
}
