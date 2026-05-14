<template>
  <div class="guide-page">
    <section class="guide-hero">
      <div>
        <p class="guide-kicker">首次使用说明</p>
        <h1>用这个系统学习、提问和巩固知识</h1>
        <p>
          系统会结合知识库文档、你的问答历史和学习画像，帮助你完成检索问答、生成练习、出综合试卷，并持续追踪掌握度。
        </p>
      </div>
      <div class="guide-actions">
        <button type="button" @click="start('/chat')">开始问答</button>
        <button class="ghost" type="button" @click="start('/knowledge')">管理知识库</button>
      </div>
    </section>

    <section class="guide-grid">
      <article class="guide-card">
        <div class="guide-icon">1</div>
        <h2>先准备知识库</h2>
        <p>
          在“知识库”中上传课程资料、讲义、PDF 或 Markdown 文件，完成入库后，问答和出题都会优先参考这些材料。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">2</div>
        <h2>像和助教聊天一样提问</h2>
        <p>
          在“问答”里直接输入问题，例如“解释一下支持向量机的间隔”或“这份资料第 3 章讲了什么”。回答会附带引用来源和追问建议。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">3</div>
        <h2>查看学习诊断</h2>
        <p>
          每次问答后，系统会记录你关注的概念、薄弱点和学习轨迹。右侧画像面板会显示当前弱项，并能一键进入针对性复习。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">4</div>
        <h2>生成学习计划和题目</h2>
        <p>
          在“学习计划”中输入概念，选择难度，系统会生成讲解、问答、填空和选择题。答题后会给出反馈，并更新该知识点掌握度。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">5</div>
        <h2>出综合试卷</h2>
        <p>
          点击“综合试卷”可以基于你的弱项和历史记录自动组卷，适合阶段复习、考前自测和检查多个概念之间的联系。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">6</div>
        <h2>持续提升掌握度</h2>
        <p>
          做完题后提交答卷，系统会根据正确率和反馈降低或提高薄弱度。你可以在“学习历史”里回看每次练习和答题记录。
        </p>
      </article>
    </section>

    <section class="guide-flow panel">
      <div>
        <h2>推荐使用流程</h2>
        <p>上传资料 -> 提问理解 -> 根据薄弱点生成练习 -> 提交答卷 -> 回看学习历史。</p>
      </div>
      <button type="button" @click="start('/review')">去生成学习计划</button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
import { authStore } from '../authStore';
import { markGuideSeen } from '../onboarding';

const router = useRouter();

function start(path: string) {
  markGuideSeen(authStore.user.value);
  router.push(path);
}
</script>
