import React from "react";
import { Button, Card } from "../ui.jsx";

/**
 * Robust Error Boundary component that catches render-time exceptions
 * in child components and displays a helpful recovery UI instead of crashing
 * or freezing the entire browser tab.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("ErrorBoundary caught an unhandled render error:", error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <Card className="my-6 border border-amber-500/30 bg-slate-900/90 p-6 text-slate-200 shadow-xl">
          <div className="flex items-start gap-4">
            <div className="rounded-lg bg-amber-500/20 p-2.5 text-amber-400">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="flex-1 space-y-2">
              <h3 className="text-base font-bold text-slate-100">Unable to display this view</h3>
              <p className="text-sm text-slate-400">
                An unexpected interface issue was caught before it could freeze the dashboard. You can retry loading this view or switch back to the Overview.
              </p>
              {this.state.error?.message && (
                <div className="rounded bg-slate-950 p-3 font-mono text-xs text-amber-300 overflow-x-auto border border-slate-800">
                  {this.state.error.message}
                </div>
              )}
              <div className="flex items-center gap-3 pt-2">
                <Button onClick={this.handleRetry}>Retry View</Button>
                {this.props.onNavigate && (
                  <Button variant="secondary" onClick={() => this.props.onNavigate("overview")}>
                    Return to Overview
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>
      );
    }
    return this.props.children;
  }
}

