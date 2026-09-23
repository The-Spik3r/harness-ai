import { EventEmitter } from "./events";
import type { Column, Row, SortDirection } from "./types";

/**
 * Base class for every table widget in the dashboard.
 *
 * Subclasses override `render()` and may override `pageSize`; the base
 * class owns sorting and change notification.
 */
export abstract class Widget<T> extends EventEmitter {
  protected readonly pageSize: number = 25;
  protected sortColumn: keyof T | null = null;
  protected sortDirection: SortDirection = "asc";

  constructor(protected readonly root: HTMLElement) {
    super();
  }

  abstract render(): void;

  get label(): string {
    return "widget";
  }

  sortBy(column: keyof T): void {
    if (this.sortColumn === column) {
      this.sortDirection = this.sortDirection === "asc" ? "desc" : "asc";
    } else {
      this.sortColumn = column;
      this.sortDirection = "asc";
    }
    this.emit("sort", { column, direction: this.sortDirection });
    this.render();
  }

  dispose(): void {
    this.removeAllListeners();
    this.root.replaceChildren();
  }
}

export class DataTable<T extends Row> extends Widget<T> {
  protected override readonly pageSize: number = 50;
  private page = 0;

  constructor(
    root: HTMLElement,
    private readonly columns: Column<T>[],
    private rows: T[],
  ) {
    super(root);
  }

  override get label(): string {
    return `table (${this.rows.length} rows)`;
  }

  setRows(rows: T[]): void {
    this.rows = rows;
    this.page = 0;
    this.render();
  }

  override render(): void {
    const start = this.page * this.pageSize;
    const visible = this.sorted().slice(start, start + this.pageSize);
    const table = document.createElement("table");
    const head = table.createTHead().insertRow();
    for (const column of this.columns) {
      const cell = head.insertCell();
      cell.textContent = column.title;
      cell.addEventListener("click", () => this.sortBy(column.key));
    }
    const body = table.createTBody();
    for (const row of visible) {
      const tr = body.insertRow();
      for (const column of this.columns) {
        tr.insertCell().textContent = String(row[column.key] ?? "");
      }
    }
    this.root.replaceChildren(table);
  }

  override dispose(): void {
    this.rows = [];
    super.dispose();
  }

  private sorted(): T[] {
    const key = this.sortColumn;
    if (key === null) {
      return this.rows;
    }
    const sign = this.sortDirection === "asc" ? 1 : -1;
    return [...this.rows].sort((a, b) => (a[key] < b[key] ? -sign : a[key] > b[key] ? sign : 0));
  }
}
