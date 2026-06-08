<template>
  <van-cell-group inset :title="title">
    <template v-if="items.length">
      <van-cell v-for="(item, index) in items" :key="`${title}-${index}`" :title="item" />
    </template>
    <van-cell v-else>
      <template #title>
        <span class="empty-text">{{ empty }}</span>
      </template>
    </van-cell>
  </van-cell-group>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  items: string[]
  empty: string
}>()
</script>
