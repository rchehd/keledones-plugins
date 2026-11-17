def setup(project, host_root, runner_data_dir, dry_run, timeout):
    return dict(component="flutter", status="PLANNED" if dry_run else "PASS", reused=True,
                reason="Flutter uses the project's installed SDK and dependencies. Run doctor for applicable prerequisites.")
