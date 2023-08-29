#!/bin/bash -l
#SBATCH --job-name="EEG_2_CoordsV"
#SBATCH --partition=prod
#SBATCH --nodes=1
#SBATCH -C clx
#SBATCH --cpus-per-task=2
#SBATCH --time=24:00:00
##SBATCH --mail-type=ALL
#SBATCH --account=proj45
#SBATCH --no-requeue
#SBATCH --output=EEG_3_CoordsV.out
#SBATCH --error=EEG_3_CoordsV.err
#SBATCH --exclusive
#SBATCH --mem=0

module purge

mkdir neuropixels

source ~/probevenv/bin/activate
srun -n 1 python writeH5_MPI_prelim_MEA_full.py 'Neuropixels-384' 'LFP' 'BlueConfig' 'positions0' 'neuropixels_full' 50 
