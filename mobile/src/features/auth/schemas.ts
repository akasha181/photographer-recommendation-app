/**
 * Client-side validation schemas.
 *
 * These MIRROR the Django serializers deliberately — same rules, same
 * messages. Client validation exists purely for speed of feedback (no
 * round-trip to tell someone their passwords don't match). The server
 * remains the authority: anything that passes here is still fully
 * re-validated in apps/accounts/serializers.py, because a client can be
 * modified and a server cannot.
 */

import { z } from 'zod';

/** Matches core.validators.PHONE_RE on the backend. */
const pakistaniPhone = /^(\+92|0)?3\d{9}$/;

export const loginSchema = z.object({
  email: z
    .string()
    .min(1, 'Email is required')
    .email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

export const registerSchema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(3, 'Please enter your full name')
      .max(120, 'Name is too long'),
    email: z
      .string()
      .min(1, 'Email is required')
      .email('Enter a valid email address'),
    phone: z
      .string()
      .trim()
      .refine((v) => v === '' || pakistaniPhone.test(v.replace(/[\s-]/g, '')), {
        message: 'Enter a valid Pakistani mobile number, e.g. 03001234567',
      })
      .optional()
      .or(z.literal('')),
    city: z.string().trim().max(80).optional().or(z.literal('')),
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .max(128, 'Password is too long')
      .refine((v) => !/^\d+$/.test(v), {
        message: 'Password cannot be entirely numeric',
      }),
    password_confirm: z.string(),
    role: z.enum(['BUYER', 'PHOTOGRAPHER']),
  })
  .refine((data) => data.password === data.password_confirm, {
    message: 'Passwords do not match',
    path: ['password_confirm'],
  });

export const forgotPasswordSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
});

export const resetPasswordSchema = z
  .object({
    email: z.string().email(),
    code: z.string().length(6, 'Enter the 6-digit code'),
    new_password: z.string().min(8, 'Password must be at least 8 characters'),
    new_password_confirm: z.string(),
  })
  .refine((data) => data.new_password === data.new_password_confirm, {
    message: 'Passwords do not match',
    path: ['new_password_confirm'],
  });

export const otpSchema = z.object({
  code: z.string().length(6, 'Enter the 6-digit code'),
});

export type LoginForm = z.infer<typeof loginSchema>;
export type RegisterForm = z.infer<typeof registerSchema>;
export type ForgotPasswordForm = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordForm = z.infer<typeof resetPasswordSchema>;
export type OtpForm = z.infer<typeof otpSchema>;
