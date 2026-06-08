<template>
  <van-popup v-model:show="visible" round :close-on-click-overlay="false" closeable @close="onClose">
    <div class="edu-login-card">
      <div class="header">
        <h3>登录吉林大学教务系统</h3>
        <p class="subtitle">
          登录后我可以帮你查询<strong>课表、成绩、考试安排和空教室</strong>。
          登录信息仅用于这四类查询，密码不会被保存，登录态过期后需要重新登录。
        </p>
        <div class="stepper">
          <span :class="['dot', { active: step === 'credential' }]">①</span>
          <span class="bar"></span>
          <span :class="['dot', { active: step === 'verify' }]">②</span>
        </div>
      </div>

      <!-- 步骤一：账号密码 -->
      <van-form v-if="step === 'credential'" @submit="goToVerifyStep" class="form">
        <van-cell-group inset>
          <van-field
            v-model="form.username"
            label="账号"
            placeholder="教务/CAS 账号"
            :rules="[{ required: true, message: '请输入账号' }]"
          />
          <van-field
            v-model="form.password"
            type="password"
            label="密码"
            placeholder="教务/CAS 密码"
            :rules="[{ required: true, message: '请输入密码' }]"
          />
        </van-cell-group>

        <div v-if="errorText" class="error-text">{{ errorText }}</div>

        <div class="actions">
          <van-button block plain @click="onClose">取消</van-button>
          <van-button block type="primary" native-type="submit" :loading="initializing">下一步</van-button>
        </div>
      </van-form>

      <!-- 步骤二：图形码 + 微信码 -->
      <van-form v-else @submit="handleConfirm" class="form">
        <div class="captcha-row">
          <van-field
            v-model="form.captcha_text"
            label="图形验证码"
            placeholder="看图输入 4 位数字"
            :rules="[{ required: true, message: '请输入图形验证码' }]"
          />
          <div class="captcha-img" @click="handleRefreshCaptcha">
            <img v-if="captchaImage" :src="captchaImage" alt="captcha" />
            <van-loading v-else size="20" />
            <div class="captcha-hint">点击换一张</div>
          </div>
        </div>

        <div class="wechat-row">
          <van-field
            v-model="form.wechat_code"
            label="微信验证码"
            placeholder="收到的验证码"
            maxlength="8"
            :disabled="!wechatSent"
          />
          <van-button
            size="small"
            type="primary"
            :loading="sending"
            :disabled="!form.captcha_text.trim() || cooldown > 0"
            class="send-btn"
            @click="handleSendWechat"
          >
            {{ sendBtnText }}
          </van-button>
        </div>

        <div v-if="errorText" class="error-text">{{ errorText }}</div>
        <div v-if="wechatSent" class="hint-text">已发送微信验证码，请到企业微信查看后填入。</div>

        <div class="actions">
          <van-button block plain @click="backToCredential">上一步</van-button>
          <van-button
            block
            type="primary"
            native-type="submit"
            :loading="confirming"
            :disabled="!wechatSent || !form.wechat_code.trim()"
          >
            确认登录
          </van-button>
        </div>
      </van-form>
    </div>
  </van-popup>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { showFailToast, showSuccessToast } from 'vant'
import {
  eduLoginConfirm,
  eduLoginInit,
  eduLoginRefreshCaptcha,
  eduLoginSendWechat,
} from '../api/client'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'update:show', v: boolean): void; (e: 'success'): void }>()

const visible = computed({
  get: () => props.show,
  set: (v: boolean) => emit('update:show', v),
})

type Step = 'credential' | 'verify'

const step = ref<Step>('credential')
const form = ref({ username: '', password: '', captcha_text: '', wechat_code: '' })
const captchaImage = ref('')
const initializing = ref(false)
const sending = ref(false)
const confirming = ref(false)
const wechatSent = ref(false)
const errorText = ref('')
const cooldown = ref(0)
let cooldownTimer: number | null = null

const sendBtnText = computed(() => {
  if (sending.value) return '发送中'
  if (cooldown.value > 0) return `${cooldown.value}s 后重发`
  return wechatSent.value ? '重新发送' : '发送微信码'
})

watch(
  () => props.show,
  (v) => {
    if (v) reset()
  },
)

function reset() {
  step.value = 'credential'
  form.value = { username: '', password: '', captcha_text: '', wechat_code: '' }
  captchaImage.value = ''
  wechatSent.value = false
  errorText.value = ''
  stopCooldown()
}

function startCooldown(seconds = 60) {
  stopCooldown()
  cooldown.value = seconds
  cooldownTimer = window.setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) stopCooldown()
  }, 1000)
}

function stopCooldown() {
  if (cooldownTimer != null) {
    clearInterval(cooldownTimer)
    cooldownTimer = null
  }
  cooldown.value = 0
}

async function goToVerifyStep() {
  errorText.value = ''
  initializing.value = true
  try {
    const res = await eduLoginInit({
      username: form.value.username.trim(),
      password: form.value.password,
    })
    captchaImage.value = res.captcha_image
    step.value = 'verify'
    wechatSent.value = false
    form.value.captcha_text = ''
    form.value.wechat_code = ''
  } catch (error: any) {
    errorText.value = error.response?.data?.detail || '获取验证码失败，请重试'
  } finally {
    initializing.value = false
  }
}

async function handleRefreshCaptcha() {
  if (!captchaImage.value) return
  try {
    const res = await eduLoginRefreshCaptcha()
    captchaImage.value = res.captcha_image
    form.value.captcha_text = ''
    errorText.value = ''
  } catch (error: any) {
    showFailToast(error.response?.data?.detail || '刷新失败')
  }
}

async function handleSendWechat() {
  errorText.value = ''
  sending.value = true
  try {
    await eduLoginSendWechat({ captcha_text: form.value.captcha_text.trim() })
    wechatSent.value = true
    showSuccessToast('已发送微信验证码')
    startCooldown(60)
  } catch (error: any) {
    errorText.value = error.response?.data?.detail || '发送失败，请检查图形码后重试'
    // 图形码错时自动换一张
    try {
      const res = await eduLoginRefreshCaptcha()
      captchaImage.value = res.captcha_image
      form.value.captcha_text = ''
    } catch {
      /* ignore */
    }
  } finally {
    sending.value = false
  }
}

async function handleConfirm() {
  errorText.value = ''
  confirming.value = true
  try {
    const res = await eduLoginConfirm({ wechat_code: form.value.wechat_code.trim() })
    showSuccessToast(`教务登录成功${res.userid ? '，学号：' + res.userid : ''}`)
    emit('success')
    onClose()
  } catch (error: any) {
    errorText.value = error.response?.data?.detail || '登录失败，请检查验证码后重试'
  } finally {
    confirming.value = false
  }
}

function backToCredential() {
  step.value = 'credential'
  wechatSent.value = false
  form.value.captcha_text = ''
  form.value.wechat_code = ''
  errorText.value = ''
  stopCooldown()
}

function onClose() {
  stopCooldown()
  emit('update:show', false)
}
</script>

<style scoped>
.edu-login-card {
  width: 92vw;
  max-width: 440px;
  padding: 18px 4px 12px;
}

.header {
  padding: 0 16px 8px;
}

.header h3 {
  margin: 0 0 8px;
  font-size: 17px;
  color: #1f2933;
}

.subtitle {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.subtitle strong {
  color: #1677ff;
}

.stepper {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  font-size: 13px;
  color: #94a3b8;
}

.stepper .dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #e2e8f0;
  color: #fff;
  text-align: center;
  line-height: 22px;
  font-weight: 600;
  font-size: 12px;
}

.stepper .dot.active {
  background: #1677ff;
}

.stepper .bar {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
}

.form {
  margin-top: 8px;
}

.captcha-row {
  display: flex;
  align-items: center;
  padding-right: 16px;
}

.captcha-row :deep(.van-cell-group),
.captcha-row :deep(.van-field) {
  flex: 1;
}

.captcha-img {
  margin-left: 12px;
  height: 50px;
  min-width: 110px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #f3f4f6;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
}

.captcha-img img {
  height: 36px;
  width: 100%;
  object-fit: contain;
}

.captcha-hint {
  font-size: 10px;
  color: #94a3b8;
  margin-top: 2px;
}

.wechat-row {
  display: flex;
  align-items: center;
  margin-top: 8px;
}

.wechat-row :deep(.van-field) {
  flex: 1;
}

.send-btn {
  margin-right: 16px;
  white-space: nowrap;
}

.error-text {
  margin: 12px 16px 0;
  color: #f56c6c;
  font-size: 13px;
}

.hint-text {
  margin: 12px 16px 0;
  color: #1677ff;
  font-size: 13px;
}

.actions {
  display: flex;
  gap: 12px;
  padding: 16px 16px 8px;
}
</style>
