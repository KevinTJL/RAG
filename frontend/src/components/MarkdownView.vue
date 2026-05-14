<template>
  <div class="markdown" v-html="html"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { marked } from 'marked';
import katex from 'katex';

const props = defineProps<{ text: string }>();

const subscriptMap: Record<string, string> = {
  '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4', '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
};
const superscriptMap: Record<string, string> = {
  '⁰': '0', '¹': '1', '²': '2', '³': '3', '⁴': '4', '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9', '⁻': '-',
};

function normalizeUnicodeMath(text: string) {
  let normalized = text.replace(/([A-Za-z])([₀₁₂₃₄₅₆₇₈₉]+)/g, (_, base, digits) => {
    return `${base}_{${[...digits].map((char) => subscriptMap[char] || char).join('')}}`;
  });
  normalized = normalized.replace(/([A-Za-z0-9)\]}])([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)/g, (_, base, digits) => {
    return `${base}^{${[...digits].map((char) => superscriptMap[char] || char).join('')}}`;
  });
  normalized = normalized.replace(/∇/g, '\\nabla ');
  return normalized;
}

function wrapBareMath(text: string, replace: (_: string, math: string, displayMode: boolean) => string) {
  let result = text;

  result = result.replace(/\[\s*([^\[\]\n]*(?:\\[a-zA-Z]+|_\{|_\w|\^\{|[A-Za-z]\([A-Za-z]\))[^\[\]\n]*)\s*\]/g, (match, math) => {
    if (!/[=\\_^]/.test(math)) return match;
    return replace(match, math, true);
  });

  result = result.replace(/([A-Za-z\\][A-Za-z0-9_{}^=+\-*/\\().,'\s]*?(?:=|\\frac|\\sum|\\nabla|_\{|_\w|\^\{|H\^\{-?1\})[A-Za-z0-9_{}^=+\-*/\\().,'\s]*)/g, (match) => {
    if (!/[=\\_^]/.test(match)) return match;
    return replace(match, match, false);
  });

  result = result.replace(/(\\(?:frac|sum|sqrt|lambda|alpha|beta|gamma|theta|mu|sigma|in|cdot|leq|geq|neq)(?:\{[^{}]*\}){0,3}(?:\^\{[^}]+\}|_\{[^}]+\})?)/g, (match) => replace(match, match, false));

  return result;
}

const html = computed(() => {
  const blocks: { id: string; math: string; displayMode: boolean }[] = [];
  let idx = 0;
  const replace = (_: string, math: string, displayMode: boolean) => {
    const id = `MathToken${idx++}End`;
    blocks.push({ id, math, displayMode });
    return id;
  };
  let safe = (props.text || '')
    .replace(/\\\\\(/g, '\\(')
    .replace(/\\\\\)/g, '\\)')
    .replace(/\\\\\[/g, '\\[')
    .replace(/\\\\\]/g, '\\]');
  safe = normalizeUnicodeMath(safe);
  safe = safe.replace(/\$\$([\s\S]+?)\$\$/g, (m, p) => replace(m, p, true));
  safe = safe.replace(/\\\[([\s\S]+?)\\\]/g, (m, p) => replace(m, p, true));
  safe = safe.replace(/\\\(([\s\S]+?)\\\)/g, (m, p) => replace(m, p, false));
  safe = safe.replace(/\$((?:\\.|[^$\\])+?)\$/g, (m, p) => replace(m, p, false));
  safe = wrapBareMath(safe, replace);
  let out = marked.parse(safe) as string;
  for (const block of blocks) {
    const rendered = katex.renderToString(block.math, { displayMode: block.displayMode, throwOnError: false });
    out = out.split(block.id).join(rendered);
  }
  return out;
});
</script>
