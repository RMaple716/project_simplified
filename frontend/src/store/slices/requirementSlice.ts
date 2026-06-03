import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Requirement } from '../services/requirementApi';

interface RequirementState {
  currentRequirement: Requirement | null;
  requirementId: string | null;
  loading: boolean;
  error: string | null;
}

const initialState: RequirementState = {
  currentRequirement: null,
  requirementId: null,
  loading: false,
  error: null,
};

const requirementSlice = createSlice({
  name: 'requirement',
  initialState,
  reducers: {
    setRequirement: (state, action: PayloadAction<Requirement>) => {
      state.currentRequirement = action.payload;
      state.requirementId = action.payload.requirement_id || null;
    },
    setRequirementId: (state, action: PayloadAction<string>) => {
      state.requirementId = action.payload;
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
    clearRequirement: (state) => {
      state.currentRequirement = null;
      state.requirementId = null;
      state.error = null;
    },
  },
});

export const { 
  setRequirement, 
  setRequirementId, 
  setLoading, 
  setError, 
  clearRequirement 
} = requirementSlice.actions;

export default requirementSlice.reducer;
