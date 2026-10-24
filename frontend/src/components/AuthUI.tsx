import React, { useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, TextInputProps, View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '@/lib/theme';

/** Purple hero on top, white sheet below. Wraps both auth screens. */
export function AuthShell({
  title, subtitle, compact, children,
}: { title: string; subtitle: string; compact?: boolean; children: React.ReactNode }) {
  return (
    <View style={s.root}>
      <StatusBar style="light" />
      <SafeAreaView edges={['top']} style={{ flex: 1 }}>
        <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
          <ScrollView
            contentContainerStyle={{ flexGrow: 1 }}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <View style={s.column}>
              <View style={[s.hero, compact && s.heroCompact]}>
                <View style={[s.circle, s.circleA]} />
                <View style={[s.circle, s.circleB]} />
                <View style={s.logo}><Text style={s.logoText}>DB</Text></View>
                <Text style={s.brand}>Draft Bench</Text>
                {!compact && <Text style={s.tagline}>Turn any document into slides, question papers and study material.</Text>}
              </View>
              <View style={s.sheet}>
                <Text style={s.title}>{title}</Text>
                <Text style={s.subtitle}>{subtitle}</Text>
                {children}
              </View>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

export function Field({ label, secureTextEntry, ...props }: { label: string } & TextInputProps) {
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(true);
  const secret = !!secureTextEntry;
  return (
    <View style={s.fieldWrap}>
      <Text style={s.label}>{label}</Text>
      <View style={[s.inputRow, focused && s.inputFocused]}>
        <TextInput
          placeholderTextColor="#A99FC0"
          autoCapitalize="none"
          autoCorrect={false}
          {...props}
          secureTextEntry={secret && hidden}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={s.input}
        />
        {secret && (
          <Pressable onPress={() => setHidden((h) => !h)} hitSlop={10}>
            <Text style={s.toggle}>{hidden ? 'Show' : 'Hide'}</Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

export function PrimaryButton({ title, onPress, loading }: { title: string; onPress: () => void; loading?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={loading}
      style={({ pressed }) => [s.button, pressed && { transform: [{ scale: 0.98 }] }, loading && { opacity: 0.8 }]}
    >
      {loading ? <ActivityIndicator color="#fff" /> : <Text style={s.buttonText}>{title}</Text>}
    </Pressable>
  );
}

export function ErrorText({ message }: { message: string }) {
  return message ? <Text style={s.error}>{message}</Text> : null;
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.primary },
  column: { flexGrow: 1, width: '100%', maxWidth: 520, alignSelf: 'center' },

  hero: { paddingHorizontal: 28, paddingTop: 36, paddingBottom: 56, overflow: 'hidden' },
  heroCompact: { paddingTop: 20, paddingBottom: 40 },
  circle: { position: 'absolute', borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.10)' },
  circleA: { width: 220, height: 220, top: -70, right: -60 },
  circleB: { width: 140, height: 140, bottom: -50, left: -40, backgroundColor: 'rgba(255,255,255,0.07)' },
  logo: {
    width: 52, height: 52, borderRadius: 16, backgroundColor: colors.paper,
    alignItems: 'center', justifyContent: 'center', marginBottom: 16,
  },
  logoText: { color: colors.primary, fontSize: 20, fontWeight: '900', letterSpacing: 0.5 },
  brand: { color: colors.paper, fontSize: 34, fontWeight: '800', letterSpacing: -0.5 },
  tagline: { color: '#DDD0FA', fontSize: 16, lineHeight: 23, marginTop: 8, maxWidth: 300 },

  sheet: {
    flexGrow: 1, backgroundColor: colors.paper, borderTopLeftRadius: 32, borderTopRightRadius: 32,
    paddingHorizontal: 24, paddingTop: 30, paddingBottom: 40, marginTop: -28,
  },
  title: { fontSize: 26, fontWeight: '800', color: colors.text },
  subtitle: { fontSize: 15, color: colors.muted, marginTop: 4, marginBottom: 24 },

  fieldWrap: { marginBottom: 16 },
  label: { fontSize: 14, fontWeight: '600', color: colors.text, marginBottom: 6 },
  inputRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: colors.soft,
    borderWidth: 1.5, borderColor: 'transparent', borderRadius: 14, paddingHorizontal: 16,
  },
  inputFocused: { borderColor: colors.primary, backgroundColor: colors.paper },
  input: {
    flex: 1, paddingVertical: 14, fontSize: 16, color: colors.text,
    ...(Platform.OS === 'web' ? ({ outlineStyle: 'none' } as any) : {}),
  },
  toggle: { color: colors.primary, fontWeight: '700', fontSize: 14, marginLeft: 8 },

  button: {
    backgroundColor: colors.primary, borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 8,
    shadowColor: colors.primary, shadowOpacity: 0.35, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 5,
  },
  buttonText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  error: {
    color: colors.danger, fontSize: 14, marginBottom: 12, backgroundColor: '#FDECEC',
    padding: 10, borderRadius: 10,
  },
});
