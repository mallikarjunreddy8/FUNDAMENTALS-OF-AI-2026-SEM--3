<template>
  <div
    style="position: relative; width: 100%; cursor: crosshair; user-select: none"
    @click="onClick"
    @mousemove="onMove"
    @mouseleave="hover = null"
  >
    <div v-html="svg" style="line-height: 0"></div>
    <template v-if="hover && ghost">
      <div v-if="ghost_range" :style="rangeStyle"></div>
      <div :style="ghostStyle">{{ ghost }}</div>
    </template>
  </div>
</template>

<script>
module.exports = {
  data() {
    return { hover: null };
  },
  computed: {
    ghostStyle() {
      return {
        position: "absolute",
        left: (this.hover.x * 100) / this.cols + "%",
        top: (this.hover.y * 100) / this.rows + "%",
        width: 100 / this.cols + "%",
        height: 100 / this.rows + "%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "18px",
        opacity: 0.8,
        outline: "2px solid white",
        borderRadius: "6px",
        background: "rgba(255, 255, 255, 0.3)",
        pointerEvents: "none",
      };
    },
    rangeStyle() {
      const r = this.ghost_range;
      return {
        position: "absolute",
        left: ((this.hover.x + 0.5 - r) * 100) / this.cols + "%",
        top: ((this.hover.y + 0.5 - r) * 100) / this.rows + "%",
        width: (2 * r * 100) / this.cols + "%",
        height: (2 * r * 100) / this.rows + "%",
        borderRadius: "50%",
        border: "2px dashed rgba(161, 98, 7, 0.8)",
        background: "rgba(253, 224, 71, 0.18)",
        pointerEvents: "none",
      };
    },
  },
  methods: {
    cellAt(e) {
      const r = this.$el.getBoundingClientRect();
      const x = Math.floor(((e.clientX - r.left) / r.width) * this.cols);
      const y = Math.floor(((e.clientY - r.top) / r.height) * this.rows);
      return x >= 0 && y >= 0 && x < this.cols && y < this.rows ? { x, y } : null;
    },
    onClick(e) {
      const cell = this.cellAt(e);
      if (cell) this.cell_click(cell);
    },
    onMove(e) {
      const cell = this.cellAt(e);
      if (!cell || !this.hover || cell.x !== this.hover.x || cell.y !== this.hover.y) {
        this.hover = cell;
      }
    },
  },
};
</script>
