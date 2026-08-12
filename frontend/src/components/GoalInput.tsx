/**
 * The single-sentence entry point plus the full intake field set
 * (implementation plan section 13).
 *
 * Validation notes worth defending:
 *  - Every required field blocks progression to the Regulation Agent. Nothing
 *    is silently defaulted — applicant status in particular is called out in
 *    section 13 as a field that must NOT assume "Saudi national".
 *  - Only cities with a built corpus are selectable; the rest are shown but
 *    disabled, so the scoping is visible rather than quietly absent.
 *  - Applicant age is collected, but an under-18 answer stops the run and
 *    points at an official source instead of inventing a minor pathway
 *    (implementation plan section 10).
 */

import { useForm } from 'react-hook-form';
import type { Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

import {
  APPLICANT_STATUSES,
  BUSINESS_CATEGORIES,
  CITIES,
  MINOR_APPLICANT_NOTICE,
  READINESS_LIMITING_FIELDS,
  intakeSchema,
  isMinorApplicant,
} from '../types/intake';
import type { IntakeValues } from '../types/intake';
import type { UploadedDocument } from '../store/caseStore';
import { DocumentUpload } from './DocumentUpload';
import styles from './GoalInput.module.css';

/** Raw control values — everything arrives from the DOM as a string. */
interface FormShape {
  goal: string;
  business_category: string;
  city: string;
  district: string;
  applicant_status: string;
  area_sqm_stated: string;
  expected_annual_revenue_sar: string;
  budget_sar: string;
  employee_count: string;
  target_opening_date: string;
  applicant_age: string;
}

const EMPTY_FORM: FormShape = {
  goal: '',
  business_category: '',
  city: '',
  district: '',
  applicant_status: '',
  area_sqm_stated: '',
  expected_annual_revenue_sar: '',
  budget_sar: '',
  employee_count: '',
  target_opening_date: '',
  applicant_age: '',
};

const SAMPLE: FormShape = {
  goal: 'I want to open a specialty coffee shop in Al-Olaya, Riyadh.',
  business_category: 'food_beverage_fixed',
  city: 'riyadh',
  district: 'Al-Olaya',
  applicant_status: 'saudi_national',
  area_sqm_stated: '120',
  expected_annual_revenue_sar: '450000',
  budget_sar: '350000',
  employee_count: '4',
  target_opening_date: '',
  applicant_age: '',
};

interface GoalInputProps {
  onSubmit: (values: IntakeValues, document: UploadedDocument | null) => void;
  document: UploadedDocument | null;
  onDocumentChange: (doc: UploadedDocument | null) => void;
  busy: boolean;
}

export function GoalInput({ onSubmit, document, onDocumentChange, busy }: GoalInputProps) {
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitted },
  } = useForm<FormShape, unknown, IntakeValues>({
    resolver: zodResolver(intakeSchema) as unknown as Resolver<FormShape, unknown, IntakeValues>,
    mode: 'onBlur',
    defaultValues: EMPTY_FORM,
  });

  const values = watch();
  const age = values.applicant_age === '' ? undefined : Number(values.applicant_age);
  const minorBlocked = isMinorApplicant(Number.isFinite(age as number) ? age : undefined);

  const missingOptional = READINESS_LIMITING_FIELDS.filter(
    (f) => !values[f.key as keyof FormShape]
  );

  const err = (name: keyof FormShape) => errors[name]?.message as string | undefined;

  const fieldProps = (name: keyof FormShape) => ({
    id: name,
    className: 'field-control',
    'aria-invalid': err(name) ? ('true' as const) : undefined,
    'aria-describedby': err(name) ? `${name}-error` : undefined,
    disabled: busy,
  });

  return (
    <form
      className={styles.form}
      onSubmit={handleSubmit((v) => onSubmit(v, document))}
      noValidate
    >
      <div className={styles.goalBlock}>
        <div className={styles.labelRow}>
          <label className={styles.goalLabel} htmlFor="goal">
            What do you want to do?
          </label>
          <button
            type="button"
            className={styles.sample}
            onClick={() => reset(SAMPLE)}
            disabled={busy}
          >
            Fill sample case
          </button>
        </div>
        <textarea
          {...fieldProps('goal')}
          {...register('goal')}
          rows={3}
          placeholder="e.g. I want to open a specialty coffee shop in Al-Olaya, Riyadh."
          className={`field-control ${styles.goalArea}`}
        />
        <FieldError name="goal" message={err('goal')} />
      </div>

      <fieldset className={styles.group} disabled={busy}>
        <legend className={styles.legend}>
          Required <span className={styles.legendHint}>— all needed before the agents run</span>
        </legend>

        <div className={styles.grid}>
          <Field label="Business category" name="business_category" error={err('business_category')}>
            <select {...fieldProps('business_category')} {...register('business_category')}>
              <option value="">Select a category…</option>
              {BUSINESS_CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="City"
            name="city"
            error={err('city')}
            hint="Only cities with a built regulation corpus are selectable."
          >
            <select {...fieldProps('city')} {...register('city')}>
              <option value="">Select a city…</option>
              {CITIES.map((c) => (
                <option key={c.value} value={c.value} disabled={!c.corpusReady}>
                  {c.label}
                  {c.corpusReady ? '' : ' — corpus not built'}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="District"
            name="district"
            error={err('district')}
            hint="Feeds the Municipal agent's competitor lookup."
          >
            <input type="text" placeholder="e.g. Al-Olaya" {...fieldProps('district')} {...register('district')} />
          </Field>

          <Field
            label="Applicant status"
            name="applicant_status"
            error={err('applicant_status')}
            hint="Determines the registration pathway — never defaulted."
          >
            <select {...fieldProps('applicant_status')} {...register('applicant_status')}>
              <option value="">Select a status…</option>
              {APPLICANT_STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>

          <Field
            label="Estimated area (sqm)"
            name="area_sqm_stated"
            error={err('area_sqm_stated')}
            hint="Checked against your uploaded lease by the Verifier."
          >
            <input
              type="number"
              min="0"
              step="any"
              placeholder="120"
              {...fieldProps('area_sqm_stated')}
              {...register('area_sqm_stated')}
            />
          </Field>

          <Field
            label="Expected annual revenue (SAR)"
            name="expected_annual_revenue_sar"
            error={err('expected_annual_revenue_sar')}
            hint="Feeds the deterministic VAT assessment."
          >
            <input
              type="number"
              min="0"
              step="any"
              placeholder="450000"
              {...fieldProps('expected_annual_revenue_sar')}
              {...register('expected_annual_revenue_sar')}
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className={styles.group} disabled={busy}>
        <legend className={styles.legend}>
          Optional <span className={styles.legendHint}>— the case proceeds without these</span>
        </legend>

        <div className={styles.grid}>
          <Field label="Budget (SAR)" name="budget_sar" error={err('budget_sar')}>
            <input type="number" min="0" step="any" {...fieldProps('budget_sar')} {...register('budget_sar')} />
          </Field>

          <Field label="Number of employees" name="employee_count" error={err('employee_count')}>
            <input type="number" min="0" step="1" {...fieldProps('employee_count')} {...register('employee_count')} />
          </Field>

          <Field label="Target opening date" name="target_opening_date" error={err('target_opening_date')}>
            <input type="date" {...fieldProps('target_opening_date')} {...register('target_opening_date')} />
          </Field>

          <Field
            label="Applicant age"
            name="applicant_age"
            error={err('applicant_age')}
            hint="Only used to detect the under-18 case."
          >
            <input type="number" min="0" step="1" {...fieldProps('applicant_age')} {...register('applicant_age')} />
          </Field>
        </div>

        {missingOptional.length > 0 && (
          <ul className={styles.limiting}>
            {missingOptional.map((f) => (
              <li key={String(f.key)}>
                <strong>{f.label}</strong> not provided — {f.why}.
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      <DocumentUpload document={document} onChange={onDocumentChange} disabled={busy} />

      {minorBlocked && (
        <div className={styles.blocked} role="alert">
          <span className={styles.blockedTitle}>Cannot proceed</span>
          <p>{MINOR_APPLICANT_NOTICE}</p>
        </div>
      )}

      <div className={styles.actions}>
        <button type="submit" className={styles.submit} disabled={busy || minorBlocked}>
          {busy ? 'Running…' : 'Start the case'}
        </button>
        {isSubmitted && Object.keys(errors).length > 0 && (
          <span className={styles.summary} role="alert">
            {Object.keys(errors).length} field
            {Object.keys(errors).length === 1 ? '' : 's'} need attention before the agents can run.
          </span>
        )}
      </div>
    </form>
  );
}

function Field({
  label,
  name,
  error,
  hint,
  children,
}: {
  label: string;
  name: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={styles.field}>
      <label className={styles.fieldLabel} htmlFor={name}>
        {label}
      </label>
      {children}
      {hint && !error && <span className={styles.hint}>{hint}</span>}
      <FieldError name={name} message={error} />
    </div>
  );
}

function FieldError({ name, message }: { name: string; message?: string }) {
  if (!message) return null;
  return (
    <span className={styles.error} id={`${name}-error`} role="alert">
      {message}
    </span>
  );
}
