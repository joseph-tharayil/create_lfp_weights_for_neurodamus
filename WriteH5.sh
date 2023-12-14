#!/bin/bash -l
#SBATCH --job-name="EEG_2_CoordsV"
#SBATCH --partition=prod
#SBATCH --nodes=10
#SBATCH -C clx
#SBATCH --cpus-per-task=2
#SBATCH --time=24:00:00
##SBATCH --mail-type=ALL
#SBATCH --account=proj45
#SBATCH --no-requeue
#SBATCH --output=EEG_S_CoordsV.out
#SBATCH --error=EEG_S_CoordsV.err
#SBATCH --exclusive
#SBATCH --mem=0


module purge

spack env activate writeCoefficientsEnv

srun -n 300 python writeH5.py 'LFP' 'BlueConfig' 'positions0' 'neuropixels_full/coeffsneuropixels.h5' 50

