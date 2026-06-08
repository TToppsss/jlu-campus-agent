<template>
  <div class="login-page">
    <div class="login-card">
      <h2>{{ isLogin ? '登录' : '注册' }}</h2>
      <van-form @submit="handleSubmit">
        <van-cell-group inset>
          <van-field
            v-model="form.username"
            name="用户名"
            label="用户名"
            placeholder="请输入用户名"
            :rules="[{ required: true, message: '请填写用户名' }]"
          />
          <van-field
            v-model="form.password"
            type="password"
            name="密码"
            label="密码"
            placeholder="请输入密码"
            :rules="[{ required: true, message: '请填写密码' }]"
          />
        </van-cell-group>
        <div style="margin: 16px;">
          <van-button round block type="primary" native-type="submit">
            {{ isLogin ? '登录' : '注册' }}
          </van-button>
          <van-button round block plain style="margin-top: 12px" @click="toggleMode">
            {{ isLogin ? '没有账号？去注册' : '已有账号？去登录' }}
          </van-button>
        </div>
      </van-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { login as apiLogin, register as apiRegister } from '../api/client'

const router = useRouter()
const isLogin = ref(true)
const form = ref({
  username: '',
  password: ''
})

const toggleMode = () => {
  isLogin.value = !isLogin.value
  form.value = { username: '', password: '' }
}

const handleSubmit = async () => {
  try {
    const action = isLogin.value ? apiLogin : apiRegister
    const response = await action(form.value)
    localStorage.setItem('access_token', response.access_token)
    localStorage.setItem('username', response.username)
    showToast({ message: isLogin.value ? '登录成功' : '注册成功', position: 'top' })
    router.push('/')
  } catch (error: any) {
    const message = error.response?.data?.detail || (isLogin.value ? '登录失败' : '注册失败')
    showToast({ message, position: 'top' })
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  background: white;
  border-radius: 16px;
  padding: 32px 24px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

h2 {
  text-align: center;
  margin: 0 0 24px 0;
  color: #333;
  font-size: 24px;
  font-weight: 600;
}
</style>
