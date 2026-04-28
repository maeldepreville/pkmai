import { Plugin, Notice, requestUrl } from 'obsidian';
import { spawn, ChildProcess } from 'child_process';
import { PkmAiSettings, DEFAULT_SETTINGS, PkmAiSettingTab } from './settings';


export default class PkmAiPlugin extends Plugin {
	settings: PkmAiSettings;

	async onload() {
		await this.loadSettings();
		
		this.addSettingTab(new PkmAiSettingTab(this.app, this));

		this.addRibbonIcon('link', 'Generate Auto-Links', async () => {
			await this.triggerApi('/api/v1/links/sync', 'Auto-Links');
		});

		this.addRibbonIcon('users', 'Generate Author Mirrors', async () => {
			await this.triggerApi('/api/v1/mirror/sync', 'Author Mirrors');
		});
	}

	async loadSettings() {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
	}

	async saveSettings() {
		await this.saveData(this.settings);
	}

	async triggerApi(endpoint: string, taskName: string) {
        if (!this.settings.vault.path) {
            new Notice(`Error: Please set your Vault Path in the PKM AI settings.`);
            return;
        }

		const statusBarItem = this.addStatusBarItem();
		statusBarItem.setText(`⏳ ${taskName}: Initializing...`);
		statusBarItem.addClass('pkmai-status-processing');

		try {
			const payload = JSON.parse(JSON.stringify(this.settings));
            payload.vault.ignored_dirs = this.settings.vault.ignored_dirs.split(',').map((s: string) => s.trim());
			const response = await requestUrl({
				url: `http://127.0.0.1:8000${endpoint}`,
				method: 'POST',
                contentType: 'application/json',
                body: JSON.stringify(payload) 
			});
			
			if (response.status === 200) {
				const taskId = response.json.task_id;
				this.pollTaskStatus(taskId, taskName, statusBarItem);
			} else {
				statusBarItem.setText(`❌ ${taskName}: Server Error`);
				setTimeout(() => statusBarItem.remove(), 5000);
			}
		} catch (error) {
			statusBarItem.setText(`❌ ${taskName}: Connection Failed`);
			setTimeout(() => statusBarItem.remove(), 5000);		}
	}

	pollTaskStatus(taskId: string, taskName: string, statusBar: HTMLElement) {
		const interval = setInterval(async () => {
			try {
				const res = await requestUrl(`http://127.0.0.1:8000/api/v1/tasks/${taskId}`);
				const status = res.json.status;

				if (status === 'completed') {
					statusBar.setText(`✅ ${taskName}: Complete!`);
					statusBar.removeClass('pkmai-status-processing');
                    statusBar.addClass('pkmai-status-success');
					clearInterval(interval);
					new Notice(`${taskName} finished successfully!`);
					
					setTimeout(() => statusBar.remove(), 5000);
					
				} else if (status === 'failed') {
					statusBar.setText(`❌ ${taskName}: Error occurred`);
					statusBar.removeClass('pkmai-status-processing');
                    statusBar.addClass('pkmai-status-error');
					clearInterval(interval);
					new Notice(`Error running ${taskName}. Check the Python terminal.`);
					setTimeout(() => statusBar.remove(), 5000);
					
				} else {
					statusBar.setText(`⏳ ${taskName}: ${status}`);
				}
			} catch (e) {
				clearInterval(interval);
				statusBar.setText(`❌ ${taskName}: Disconnected`);
				setTimeout(() => statusBar.remove(), 5000);
			}
		}, 1000);
	}
}
