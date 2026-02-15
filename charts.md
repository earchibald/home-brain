
graph TD
    subgraph "NUC-3: Storage Hub (nuc-3.local)"
        SyncMaster[Syncthing Master Node]
        Backup[Restic Backup]
        FS_Master[Primary Brain Folder]
        SyncMaster <--> FS_Master
        Backup --> S3_Cloud[(Offsite S3)]
    end

    subgraph "NUC-1: Librarian (nuc-1.local)"
        Khoj[Khoj App]
        DB[(Postgres)]
        FS_NUC1[Synced Brain Folder]
        Khoj <--> DB
        Khoj -- "Index" --> FS_NUC1
        FS_NUC1 <--> SyncMaster
    end

    subgraph "NUC-2: Automation (nuc-2.local)"
        Agents[Python Agents]
        Scrapers[Web Scrapers]
        FS_NUC2[Synced Brain Folder]
        Agents -- "Read/Write" --> FS_NUC2
        FS_NUC2 <--> SyncMaster
    end

    subgraph "Mac Mini (m1-mini.local)"
        Ollama[Ollama API]
        Llama[Llama 3.2]
        Nomic[Nomic-Embed]
        Ollama --> Llama
        Ollama --> Nomic
    end

    Laptop[Laptop Client]
    Laptop -- "Control" --> Khoj
    Laptop <--> SyncMaster
    Khoj -- "Inference" --> Ollama
