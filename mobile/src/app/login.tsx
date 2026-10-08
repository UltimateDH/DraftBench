import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';
import { Link } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { AuthShell, ErrorText, Field, PrimaryButton } from '@/components/AuthUI';
import { colors } from '@/lib/theme';

export default function Login() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!username.trim() || !password) return setError('Enter your username and password.');
    setError('');
    setLoading(true);
    try {
      await signIn(username.trim(), password);
      // The root layout switches to (app) once `user` is set.
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Welcome back" subtitle="Log in to continue to your materials.">
      <Field label="Username" value={username} onChangeText={setUsername} textContentType="username" />
      <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry textContentType="password" onSubmitEditing={submit} />
      <ErrorText message={error} />
      <PrimaryButton title="Log in" onPress={submit} loading={loading} />
      <Text style={s.switch}>
        New here? <Link href="/signup" style={s.link}>Create an account</Link>
      </Text>
    </AuthShell>
  );
}

const s = StyleSheet.create({
  switch: { textAlign: 'center', marginTop: 22, color: colors.muted, fontSize: 15 },
  link: { color: colors.primary, fontWeight: '700' },
});