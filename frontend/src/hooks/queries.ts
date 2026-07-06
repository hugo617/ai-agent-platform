import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  addMember,
  createAgent,
  createTenant,
  deleteAgent,
  fetchAgents,
  fetchMe,
  fetchMembers,
  fetchTenants,
  removeMember,
  updateAgent,
  updateMember,
} from "@/api/endpoints";
import type { AgentCreate, AgentUpdate, MemberCreate, MemberUpdate } from "@/api/types";

// Query key factory — centralised so cache invalidation is consistent.
export const qk = {
  me: ["auth", "me"] as const,
  tenants: ["tenants"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  members: ["members"] as const,
};

// ---------- auth ----------
export function useMe() {
  return useQuery({ queryKey: qk.me, queryFn: fetchMe });
}

// ---------- tenants ----------
export function useTenants() {
  return useQuery({ queryKey: qk.tenants, queryFn: fetchTenants });
}

export function useCreateTenant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => createTenant(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.tenants }),
  });
}

// ---------- agents ----------
export function useAgents() {
  return useQuery({ queryKey: qk.agents, queryFn: fetchAgents });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AgentCreate) => createAgent(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: AgentUpdate }) =>
      updateAgent(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAgent(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.agents }),
  });
}

// ---------- members ----------
export function useMembers() {
  return useQuery({ queryKey: qk.members, queryFn: fetchMembers });
}

export function useAddMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: MemberCreate) => addMember(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members }),
  });
}

export function useUpdateMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: MemberUpdate }) =>
      updateMember(userId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members }),
  });
}

export function useRemoveMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeMember(userId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.members }),
  });
}
