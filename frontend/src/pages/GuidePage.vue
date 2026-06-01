<template>
  <div class="guide-page">
    <section class="guide-hero">
      <div>
        <p class="guide-kicker">首次使用说明</p>
        <h1>用这个系统学习、提问和巩固知识</h1>
        <p>
          系统会结合公共知识库、个人资料、问答历史、长期记忆和学习画像，帮助你完成课程问答、资料追溯、薄弱点复习和综合自测。
        </p>
      </div>
      <div class="guide-actions">
        <button type="button" @click="start('/chat')">开始问答</button>
        <button class="ghost" type="button" @click="start('/knowledge')">管理知识库</button>
        <button class="ghost" type="button" @click="start('/settings')">调整设置</button>
      </div>
    </section>

    <section class="guide-grid">
      <article class="guide-card">
        <div class="guide-icon">1</div>
        <h2>准备公共和个人知识库</h2>
        <p>
          在“知识库”中查看系统公共资料，也可以上传自己的 TXT、Markdown 或 PDF 文件。系统会自动解析、分块、向量化，后续问答会同时利用课程资料和个人笔记。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">2</div>
        <h2>设置检索范围和模型</h2>
        <p>
          在“用户设置”里选择检索全部资料、仅个人资料或仅系统资料，也可以勾选参与检索的具体文件。需要更强模型时，可切换 DeepSeek thinking 或配置 OpenAI 兼容模型。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">3</div>
        <h2>按主题建立多个对话</h2>
        <p>
          在“问答”里可以新建多个对话窗口，把算法原理、公式推导、课程复习等主题分开整理。系统会结合最近会话历史改写追问，让连续提问更自然。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">4</div>
        <h2>查看回答依据和原文</h2>
        <p>
          每次回答都会返回引用片段、来源文件和页码。点击引用可以打开资料预览，Markdown 会直接渲染，PDF 可按页查看，方便你核对教材或讲义原文。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">5</div>
        <h2>查看学习诊断</h2>
        <p>
          每次问答后，系统会记录你关注的概念、可能误区和长期学习轨迹。右侧画像面板会显示当前弱项、推荐复习内容，并能一键进入针对性练习。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">6</div>
        <h2>生成专题练习</h2>
        <p>
          在“学习计划”中输入概念并选择难度，系统会生成讲解、单选题、填空题和答题反馈。题目会尽量避开历史重复内容，答题后自动更新薄弱度。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">7</div>
        <h2>出综合试卷</h2>
        <p>
          点击“综合试卷”可以基于完整学习画像、薄弱概念、知识漏洞和常见误区自动组卷，适合阶段复习、考前自测和检查多个概念之间的联系。
        </p>
      </article>

      <article class="guide-card">
        <div class="guide-icon">8</div>
        <h2>持续提升掌握度</h2>
        <p>
          做完题后提交答卷，系统会根据正确率调整下一套题难度，并降低或提高对应概念的薄弱度。你可以在“学习历史”里回看每次练习和答题记录。
        </p>
      </article>
    </section>

    <section class="guide-flow panel">
      <div>
        <h2>推荐使用流程</h2>
        <p>上传资料 -> 调整检索范围 -> 按主题提问 -> 查看引用与画像 -> 生成练习或综合试卷 -> 提交答卷 -> 回看学习历史。</p>
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
