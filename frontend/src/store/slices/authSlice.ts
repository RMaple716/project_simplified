import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { authApi } from '../../services/authApi';

interface UserInfo {
  user_id: string;
  username: string;
  email: string;
  avatar: string | null;
}

interface AuthState {
  isLoggedIn: boolean;
  token: string | null;
  user: UserInfo | null;
  loading: boolean;
}

const initialState: AuthState = {
  isLoggedIn: !!localStorage.getItem('token'),
  token: localStorage.getItem('token'),
  user: localStorage.getItem('username')
    ? { 
        user_id: localStorage.getItem('user_id') || '', 
        username: localStorage.getItem('username') || '', 
        email: localStorage.getItem('email') || '', 
        avatar: null 
      }
    : null,
  loading: false,
};

export const fetchCurrentUser = createAsyncThunk(
  'auth/fetchCurrentUser',
  async (_, { rejectWithValue }) => {
    try {
      const res = await authApi.getCurrentUser();
      if (res.code === 200) {
        return res.data;
      }
      return rejectWithValue(res.msg);
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.detail || '获取用户信息失败');
    }
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginSuccess(state, action: PayloadAction<{ token: string; user_id: string; username: string }>) {
      state.isLoggedIn = true;
      state.token = action.payload.token;
      state.user = {
        user_id: action.payload.user_id,
        username: action.payload.username,
        email: '',
        avatar: null,
      };
    },
    logout(state) {
      state.isLoggedIn = false;
      state.token = null;
      state.user = null;
      localStorage.removeItem('token');
      localStorage.removeItem('user_id');
      localStorage.removeItem('username');
    },
    setUser(state, action: PayloadAction<UserInfo>) {
      state.user = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchCurrentUser.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchCurrentUser.fulfilled, (state, action) => {
        state.loading = false;
        state.user = action.payload;
        state.isLoggedIn = true;
      })
      .addCase(fetchCurrentUser.rejected, (state) => {
        state.loading = false;
        state.isLoggedIn = false;
        state.token = null;
        state.user = null;
        localStorage.removeItem('token');
        localStorage.removeItem('user_id');
        localStorage.removeItem('username');
      });
  },
});

export const { loginSuccess, logout, setUser } = authSlice.actions;
export default authSlice.reducer;