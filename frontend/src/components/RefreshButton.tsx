interface RefreshButtonProps {
  disabled: boolean;
  onRefresh: () => void;
}

export function RefreshButton({ disabled, onRefresh }: RefreshButtonProps) {
  return (
    <button
      type="button"
      onClick={onRefresh}
      disabled={disabled}
      className="inline-flex min-h-11 items-center justify-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-900 shadow-sm transition hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
    >
      {disabled ? "Refresh in progress" : "Refresh status"}
    </button>
  );
}
